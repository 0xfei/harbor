#!/bin/bash
# solution/solve.sh — ClickHouse to Doris 完整迁移方案
set -e

echo "=== Step 1: Create ClickHouse Source Table ==="
clickhouse-client --multiquery << 'EOF'
CREATE DATABASE IF NOT EXISTS ads;

CREATE TABLE IF NOT EXISTS ads.seller_item_stat
(
    p_date        Date,
    seller_id     String,
    item_id       String,
    category_id   Int32,
    sub_cat_name  String,
    imp_cnt       UInt64,
    clk_cnt       UInt64,
    order_cnt     UInt32,
    order_amt     Float64,
    refund_cnt    UInt32,
    refund_amt    Float64,

    INDEX idx_item_id   item_id     TYPE bloom_filter GRANULARITY 4,
    INDEX idx_category  category_id TYPE set(0)       GRANULARITY 4
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(p_date)
ORDER BY (p_date, seller_id, item_id, category_id)
SETTINGS index_granularity = 8192;
EOF

echo "=== Step 2: Generate Test Data in ClickHouse ==="
python3 /app/generate_data.py

echo "=== Step 3: Create Doris Optimized Table ==="
mysql -h127.0.0.1 -P9030 -uroot << 'EOF'
CREATE DATABASE IF NOT EXISTS ads;
USE ads;

-- 优化版表结构：Key 覆盖最高频查询
DROP TABLE IF EXISTS seller_item_stat;

CREATE TABLE seller_item_stat (
    -- Key 列：只放最高频过滤维度，保证前缀索引完整命中
    seller_id     VARCHAR(32)  NOT NULL COMMENT '卖家ID - 21字节，首列，Q1直接命中',
    p_date        DATE         NOT NULL COMMENT '日期分区 - 3字节，累计24字节',
    
    -- 非 Key 列（依赖 Inverted Index / ROLLUP 补偿）
    item_id       VARCHAR(64)  NOT NULL COMMENT '商品ID',
    category_id   INT          NOT NULL DEFAULT '0' COMMENT '品类ID',
    sub_cat_name  VARCHAR(64)  COMMENT '子品类名称',
    imp_cnt       BIGINT       DEFAULT '0' COMMENT '曝光数',
    clk_cnt       BIGINT       DEFAULT '0' COMMENT '点击数',
    order_cnt     INT          DEFAULT '0' COMMENT '订单数',
    order_amt     DOUBLE       DEFAULT '0' COMMENT '订单金额',
    refund_cnt    INT          DEFAULT '0' COMMENT '退款数',
    refund_amt    DOUBLE       DEFAULT '0' COMMENT '退款金额',

    -- Inverted Index 补偿非首列过滤
    INDEX idx_item_id  (item_id)    USING INVERTED PROPERTIES("parser"="none"),
    INDEX idx_category (category_id) USING INVERTED

) ENGINE = OLAP
DUPLICATE KEY(seller_id, p_date)
PARTITION BY RANGE(p_date)(
    FROM ("2025-01-01") TO ("2026-01-01") INTERVAL 1 MONTH
)
DISTRIBUTED BY HASH(seller_id) BUCKETS 1
PROPERTIES(
    "replication_num" = "1",
    "compaction_policy" = "time_series",
    "bloom_filter_columns" = "seller_id"
);

-- ROLLUP：为 category_id 过滤优化 (Q3)
ALTER TABLE seller_item_stat
ADD ROLLUP r_category (
    category_id, p_date, seller_id, item_id,
    imp_cnt, clk_cnt, order_cnt, order_amt, refund_cnt, refund_amt
);
EOF

echo "=== Step 4: Migrate Data from ClickHouse to Doris ==="
# 导出 ClickHouse 数据为 CSV
clickhouse-client --query "
SELECT 
    seller_id, 
    formatDateTime(p_date, '%Y-%m-%d') as p_date,
    item_id, 
    category_id, 
    sub_cat_name, 
    imp_cnt, 
    clk_cnt, 
    order_cnt, 
    order_amt, 
    refund_cnt, 
    refund_amt
FROM ads.seller_item_stat
FORMAT CSV
" > /data/export.csv

echo "Exported $(wc -l < /data/export.csv) rows from ClickHouse"

# 导入 Doris via Stream Load
curl --location-trusted -u root: \
    -H "column_separator:," \
    -H "columns:seller_id,p_date,item_id,category_id,sub_cat_name,imp_cnt,clk_cnt,order_cnt,order_amt,refund_cnt,refund_amt" \
    -T /data/export.csv \
    http://127.0.0.1:8030/api/ads/seller_item_stat/_stream_load

echo "=== Step 5: Verify Data Consistency ==="
CH_COUNT=$(clickhouse-client --query "SELECT count() FROM ads.seller_item_stat" 2>/dev/null || echo "0")
DORIS_COUNT=$(mysql -h127.0.0.1 -P9030 -uroot -N -e "SELECT count(*) FROM ads.seller_item_stat" 2>/dev/null || echo "0")

echo "ClickHouse rows: $CH_COUNT"
echo "Doris rows: $DORIS_COUNT"

if [ "$CH_COUNT" = "$DORIS_COUNT" ]; then
    echo "✅ Data migration verified"
else
    echo "❌ Data count mismatch!"
    exit 1
fi

echo "=== Step 6: Create Query Views ==="
# 无需创建视图，直接执行优化后的查询

echo "=== Migration Complete ==="
