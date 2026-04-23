#!/bin/bash
# 完整的 ClickHouse vs Doris 性能对比测试
set -e

echo "=========================================="
echo "ClickHouse vs Doris Performance Comparison"
echo "=========================================="

# 配置
CH_HOST="${CH_HOST:-clickhouse}"
CH_PORT="${CH_PORT:-9000}"
DORIS_HOST="${DORIS_HOST:-doris-fe}"
DORIS_PORT="${DORIS_PORT:-9030}"

# 等待服务就绪
wait_for_clickhouse() {
    echo "[1/10] Waiting for ClickHouse..."
    for i in {1..60}; do
        if clickhouse-client --host $CH_HOST --port $CH_PORT --query "SELECT 1" >/dev/null 2>&1; then
            echo "✓ ClickHouse is ready"
            return 0
        fi
        sleep 2
    done
    echo "✗ ClickHouse not ready after 120s"
    return 1
}

wait_for_doris() {
    echo "[2/10] Waiting for Doris FE..."
    for i in {1..60}; do
        if mysql -h$DORIS_HOST -P$DORIS_PORT -uroot -e "SELECT 1" >/dev/null 2>&1; then
            echo "✓ Doris FE is ready"
            return 0
        fi
        sleep 2
    done
    echo "✗ Doris FE not ready after 120s"
    return 1
}

# 创建 ClickHouse 表并插入数据
setup_clickhouse() {
    echo "[3/10] Setting up ClickHouse table..."
    
    clickhouse-client --host $CH_HOST --port $CH_PORT --multiquery << 'EOF'
CREATE DATABASE IF NOT EXISTS ads;

DROP TABLE IF EXISTS ads.seller_item_stat;

CREATE TABLE ads.seller_item_stat (
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

    echo "[4/10] Inserting data into ClickHouse (100K rows)..."
    clickhouse-client --host $CH_HOST --port $CH_PORT --query "
    INSERT INTO ads.seller_item_stat
    SELECT
        toDate('2025-04-01') + number % 22 as p_date,
        'S_' || toString(number % 1000 + 10000) as seller_id,
        'ITEM_' || toString(number % 10000 + 100000) as item_id,
        number % 100 + 1 as category_id,
        'cat_' || toString(number % 100) as sub_cat_name,
        rand() % 10000 + 100 as imp_cnt,
        rand() % 1000 + 10 as clk_cnt,
        rand() % 100 as order_cnt,
        round(rand() % 10000 + 100, 2) as order_amt,
        rand() % 10 as refund_cnt,
        round(rand() % 100, 2) as refund_amt
    FROM numbers(100000)
    "
    
    CH_COUNT=$(clickhouse-client --host $CH_HOST --port $CH_PORT --query "SELECT count() FROM ads.seller_item_stat")
    echo "✓ ClickHouse: $CH_COUNT rows inserted"
}

# 创建 Doris 表并插入数据
setup_doris() {
    echo "[5/10] Setting up Doris table..."
    
    mysql -h$DORIS_HOST -P$DORIS_PORT -uroot << 'EOF'
CREATE DATABASE IF NOT EXISTS ads;
USE ads;

DROP TABLE IF EXISTS seller_item_stat;

-- 优化版表结构
CREATE TABLE seller_item_stat (
    -- Key 列：seller_id 首列用于 Q1 优化
    seller_id     VARCHAR(32)  NOT NULL COMMENT '卖家ID',
    p_date        DATE         NOT NULL COMMENT '日期分区',
    
    -- 非 Key 列
    item_id       VARCHAR(64)  NOT NULL COMMENT '商品ID',
    category_id   INT          NOT NULL DEFAULT '0' COMMENT '品类ID',
    sub_cat_name  VARCHAR(64)  NULL COMMENT '子品类名称',
    imp_cnt       BIGINT       DEFAULT '0' COMMENT '曝光数',
    clk_cnt       BIGINT       DEFAULT '0' COMMENT '点击数',
    order_cnt     INT          DEFAULT '0' COMMENT '订单数',
    order_amt     DOUBLE       DEFAULT '0' COMMENT '订单金额',
    refund_cnt    INT          DEFAULT '0' COMMENT '退款数',
    refund_amt    DOUBLE       DEFAULT '0' COMMENT '退款金额',

    -- 倒排索引
    INDEX idx_item_id  (item_id)    USING INVERTED PROPERTIES("parser"="none"),
    INDEX idx_category (category_id) USING INVERTED

) ENGINE = OLAP
DUPLICATE KEY(seller_id, p_date)
PARTITION BY RANGE(p_date)(
    FROM ("2025-04-01") TO ("2025-05-01") INTERVAL 1 DAY
)
DISTRIBUTED BY HASH(seller_id) BUCKETS 4
PROPERTIES(
    "replication_num" = "1",
    "compaction_policy" = "time_series"
);
EOF

    echo "[6/10] Migrating data from ClickHouse to Doris..."
    
    # 导出 CH 数据为 CSV
    clickhouse-client --host $CH_HOST --port $CH_PORT --query "
    SELECT 
        seller_id,
        formatDateTime(p_date, '%Y-%m-%d'),
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
    " > /tmp/ch_data.csv
    
    echo "Exported $(wc -l < /tmp/ch_data.csv) rows from ClickHouse"
    
    # 导入 Doris via Stream Load
    curl --location-trusted -u root: \
        -H "column_separator:," \
        -H "columns:seller_id,p_date,item_id,category_id,sub_cat_name,imp_cnt,clk_cnt,order_cnt,order_amt,refund_cnt,refund_amt" \
        -T /tmp/ch_data.csv \
        "http://${DORIS_HOST}:8030/api/ads/seller_item_stat/_stream_load" 2>/dev/null
    
    sleep 3
    
    DORIS_COUNT=$(mysql -h$DORIS_HOST -P$DORIS_PORT -uroot -N -e "SELECT count(*) FROM ads.seller_item_stat" 2>/dev/null)
    echo "✓ Doris: $DORIS_COUNT rows inserted"
    
    # 创建 ROLLUP 用于 Q3
    echo "[7/10] Creating ROLLUP for Q3 optimization..."
    mysql -h$DORIS_HOST -P$DORIS_PORT -uroot << 'EOF' 2>/dev/null || true
ALTER TABLE ads.seller_item_stat
ADD ROLLUP r_category (
    category_id, p_date, seller_id, item_id,
    imp_cnt, clk_cnt, order_cnt, order_amt, refund_cnt, refund_amt
);
EOF
    sleep 5
}

# 运行性能测试
run_benchmark() {
    echo ""
    echo "=========================================="
    echo "Running Performance Benchmark"
    echo "=========================================="
    
    # Q1: 卖家看板
    echo ""
    echo "--- Q1: Seller Dashboard ---"
    
    echo "ClickHouse:"
    time clickhouse-client --host $CH_HOST --port $CH_PORT --query "
    SELECT seller_id, sum(imp_cnt) as imp, sum(clk_cnt) as clk, sum(order_amt) as gmv
    FROM ads.seller_item_stat
    WHERE p_date BETWEEN '2025-04-16' AND '2025-04-22'
      AND seller_id = 'S_10012'
    GROUP BY seller_id
    " 2>&1
    
    echo ""
    echo "Doris:"
    time mysql -h$DORIS_HOST -P$DORIS_PORT -uroot -e "
    SELECT seller_id, sum(imp_cnt) as imp, sum(clk_cnt) as clk, sum(order_amt) as gmv
    FROM ads.seller_item_stat
    WHERE p_date BETWEEN '2025-04-16' AND '2025-04-22'
      AND seller_id = 'S_10012'
    GROUP BY seller_id
    " 2>&1
    
    # Q2: 商品趋势
    echo ""
    echo "--- Q2: Item Trend ---"
    
    echo "ClickHouse:"
    time clickhouse-client --host $CH_HOST --port $CH_PORT --query "
    SELECT p_date, sum(imp_cnt) as imp, sum(order_amt) as gmv
    FROM ads.seller_item_stat
    WHERE item_id = 'ITEM_100000'
      AND p_date BETWEEN '2025-04-01' AND '2025-04-22'
    GROUP BY p_date ORDER BY p_date
    " 2>&1
    
    echo ""
    echo "Doris:"
    time mysql -h$DORIS_HOST -P$DORIS_PORT -uroot -e "
    SELECT p_date, sum(imp_cnt) as imp, sum(order_amt) as gmv
    FROM ads.seller_item_stat
    WHERE item_id = 'ITEM_100000'
      AND p_date BETWEEN '2025-04-01' AND '2025-04-22'
    GROUP BY p_date ORDER BY p_date
    " 2>&1
    
    # Q3: 品类分析
    echo ""
    echo "--- Q3: Category Analysis ---"
    
    echo "ClickHouse:"
    time clickhouse-client --host $CH_HOST --port $CH_PORT --query "
    SELECT seller_id, sum(order_amt) as gmv
    FROM ads.seller_item_stat
    WHERE category_id = 50
    GROUP BY seller_id
    ORDER BY gmv DESC LIMIT 10
    " 2>&1
    
    echo ""
    echo "Doris:"
    time mysql -h$DORIS_HOST -P$DORIS_PORT -uroot -e "
    SELECT seller_id, sum(order_amt) as gmv
    FROM ads.seller_item_stat
    WHERE category_id = 50
    GROUP BY seller_id
    ORDER BY gmv DESC LIMIT 10
    " 2>&1
}

# 验证结果一致性
verify_consistency() {
    echo ""
    echo "=========================================="
    echo "Verifying Data Consistency"
    echo "=========================================="
    
    # 检查行数
    CH_COUNT=$(clickhouse-client --host $CH_HOST --port $CH_PORT --query "SELECT count() FROM ads.seller_item_stat")
    DORIS_COUNT=$(mysql -h$DORIS_HOST -P$DORIS_PORT -uroot -N -e "SELECT count(*) FROM ads.seller_item_stat" 2>/dev/null)
    
    echo "ClickHouse rows: $CH_COUNT"
    echo "Doris rows:      $DORIS_COUNT"
    
    if [ "$CH_COUNT" = "$DORIS_COUNT" ]; then
        echo "✓ Row count matches"
    else
        echo "✗ Row count mismatch!"
    fi
    
    # 检查聚合结果
    echo ""
    echo "Checking Q1 aggregation..."
    
    CH_Q1=$(clickhouse-client --host $CH_HOST --port $CH_PORT --query "
    SELECT sum(order_amt) FROM ads.seller_item_stat WHERE seller_id = 'S_10012'
    ")
    
    DORIS_Q1=$(mysql -h$DORIS_HOST -P$DORIS_PORT -uroot -N -e "
    SELECT sum(order_amt) FROM ads.seller_item_stat WHERE seller_id = 'S_10012'
    " 2>/dev/null)
    
    echo "ClickHouse GMV: $CH_Q1"
    echo "Doris GMV:      $DORIS_Q1"
    
    if [ "$CH_Q1" = "$DORIS_Q1" ]; then
        echo "✓ Q1 results match"
    else
        echo "✗ Q1 results differ"
    fi
}

# 主流程
main() {
    wait_for_clickhouse || exit 1
    wait_for_doris || exit 1
    
    setup_clickhouse
    setup_doris
    
    run_benchmark
    verify_consistency
    
    echo ""
    echo "=========================================="
    echo "Test Complete!"
    echo "=========================================="
}

main "$@"
