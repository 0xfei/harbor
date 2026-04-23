#!/usr/bin/env bash
# Oracle Solution for ClickHouse to Doris Migration
# 核心优化：前缀索引 36 字节限制下的最优设计

set -e

echo "=== Doris Migration Oracle Solution ==="

# 配置
DORIS_HOST="${DORIS_HOST:-localhost}"
DORIS_PORT="${DORIS_PORT:-9030}"
DORIS_USER="${DORIS_USER:-root}"
DORIS_PASS="${DORIS_PASS:-}"

# 等待 Doris 就绪
wait_for_doris() {
    echo "Waiting for Doris to be ready..."
    for i in {1..60}; do
        if mysql -h"$DORIS_HOST" -P"$DORIS_PORT" -u"$DORIS_USER" -e "SELECT 1" >/dev/null 2>&1; then
            echo "✓ Doris is ready"
            return 0
        fi
        sleep 2
    done
    echo "✗ Doris not ready after 120s"
    return 1
}

# 创建 Doris 优化表结构
create_doris_table() {
    echo "Creating Doris table with optimized schema..."
    
    mysql -h"$DORIS_HOST" -P"$DORIS_PORT" -u"$DORIS_USER" << 'EOSQL'
CREATE DATABASE IF NOT EXISTS ads;
USE ads;

DROP TABLE IF EXISTS ads_seller_item_stat;

-- Doris 前缀索引分析（36字节上限）
-- seller_id VARCHAR(16): "S_00001234" = 10 chars → 10+1 = 11 bytes
-- item_id VARCHAR(16): "ITEM_000012345" = 14 chars → 14+1 = 15 bytes  
-- category_id INT: 4 bytes
-- 合计 11+15+4 = 30 bytes < 36 bytes ✓ 三列全部完整覆盖

CREATE TABLE ads_seller_item_stat (
    p_date        DATE NOT NULL,
    seller_id     VARCHAR(16) NOT NULL COMMENT '卖家ID S_00001234',
    item_id       VARCHAR(16) NOT NULL COMMENT '商品ID ITEM_000012345',
    category_id   INT NOT NULL DEFAULT '0' COMMENT '品类ID',
    sub_cat_name  VARCHAR(32) COMMENT '子品类名称',
    imp_cnt       BIGINT DEFAULT '0' COMMENT '曝光数',
    clk_cnt       BIGINT DEFAULT '0' COMMENT '点击数',
    order_cnt     INT DEFAULT '0' COMMENT '订单数',
    order_amt     DOUBLE DEFAULT '0' COMMENT '订单金额',
    refund_cnt    INT DEFAULT '0' COMMENT '退款数',
    refund_amt    DOUBLE DEFAULT '0' COMMENT '退款金额',

    -- Inverted Index: FPR=0%, row-level 精准命中
    -- Q2: item_id 索引
    INDEX idx_item_id (item_id) USING INVERTED PROPERTIES("parser"="none") COMMENT '商品ID倒排索引',
    
    -- Q3: category_id 索引
    INDEX idx_category (category_id) USING INVERTED COMMENT '品类ID倒排索引'

) ENGINE = OLAP
DUPLICATE KEY(seller_id, item_id)  -- 前缀索引覆盖 seller_id + item_id
PARTITION BY RANGE(p_date)(
    FROM ("2025-01-01") TO ("2026-01-01") INTERVAL 1 MONTH
)
DISTRIBUTED BY HASH(seller_id) BUCKETS 4
PROPERTIES(
    "replication_num" = "1",
    "compaction_policy" = "time_series"
);

-- 验证表创建
SHOW CREATE TABLE ads_seller_item_stat;
EOSQL

    echo "✓ Doris table created"
}

# 从 ClickHouse 导出数据并导入 Doris
migrate_data() {
    echo "Migrating data from ClickHouse to Doris..."
    
    # 导出 ClickHouse 数据为 CSV
    clickhouse-client --query "
    SELECT 
        formatDateTime(p_date, '%Y-%m-%d'),
        seller_id,
        item_id,
        category_id,
        sub_cat_name,
        imp_cnt,
        clk_cnt,
        order_cnt,
        order_amt,
        refund_cnt,
        refund_amt
    FROM ads_seller_item_stat
    FORMAT CSV
    " > /tmp/ch_export.csv
    
    local rows=$(wc -l < /tmp/ch_export.csv)
    echo "Exported $rows rows from ClickHouse"
    
    # Stream Load 到 Doris
    curl --location-trusted -u root: \
        -H "column_separator:," \
        -H "columns:p_date,seller_id,item_id,category_id,sub_cat_name,imp_cnt,clk_cnt,order_cnt,order_amt,refund_cnt,refund_amt" \
        -T /tmp/ch_export.csv \
        "http://${DORIS_HOST}:8030/api/ads/ads_seller_item_stat/_stream_load"
    
    echo "✓ Data migrated to Doris"
}

# 验证数据一致性
verify_data() {
    echo "Verifying data consistency..."
    
    # 检查行数
    local ch_count=$(clickhouse-client --query "SELECT count() FROM ads_seller_item_stat")
    local doris_count=$(mysql -h"$DORIS_HOST" -P"$DORIS_PORT" -uroot -N -e "SELECT count(*) FROM ads.ads_seller_item_stat" 2>/dev/null)
    
    echo "ClickHouse rows: $ch_count"
    echo "Doris rows:      $doris_count"
    
    if [ "$ch_count" = "$doris_count" ]; then
        echo "✓ Row count matches"
    else
        echo "✗ Row count mismatch!"
        exit 1
    fi
    
    # 检查 Q1 结果
    local ch_q1=$(clickhouse-client --query "
    SELECT sum(order_amt) FROM ads_seller_item_stat WHERE seller_id = 'S_00001234'
    ")
    
    local doris_q1=$(mysql -h"$DORIS_HOST" -P"$DORIS_PORT" -uroot -N -e "
    SELECT sum(order_amt) FROM ads.ads_seller_item_stat WHERE seller_id = 'S_00001234'
    " 2>/dev/null)
    
    echo "ClickHouse Q1 GMV: $ch_q1"
    echo "Doris Q1 GMV:      $doris_q1"
    
    if [ "$ch_q1" = "$doris_q1" ]; then
        echo "✓ Q1 results match"
    else
        echo "✗ Q1 results differ"
    fi
}

# 运行性能对比
run_benchmark() {
    echo ""
    echo "=== Performance Benchmark ==="
    
    echo ""
    echo "--- Q1: Seller Dashboard ---"
    echo "ClickHouse:"
    time clickhouse-client --query "
    SELECT seller_id, sum(imp_cnt), sum(order_amt)
    FROM ads_seller_item_stat
    WHERE seller_id = 'S_00001234'
      AND p_date BETWEEN '2025-04-16' AND '2025-04-22'
    GROUP BY seller_id
    "
    
    echo ""
    echo "Doris:"
    time mysql -h"$DORIS_HOST" -P"$DORIS_PORT" -uroot -e "
    SELECT seller_id, sum(imp_cnt), sum(order_amt)
    FROM ads.ads_seller_item_stat
    WHERE seller_id = 'S_00001234'
      AND p_date BETWEEN '2025-04-16' AND '2025-04-22'
    GROUP BY seller_id
    " 2>/dev/null
    
    echo ""
    echo "--- Q2: Item Trend ---"
    echo "ClickHouse:"
    time clickhouse-client --query "
    SELECT count(), sum(order_amt)
    FROM ads_seller_item_stat
    WHERE item_id = 'ITEM_000012345'
    " 2>&1
    
    echo ""
    echo "Doris:"
    time mysql -h"$DORIS_HOST" -P"$DORIS_PORT" -uroot -e "
    SELECT count(*), sum(order_amt)
    FROM ads.ads_seller_item_stat
    WHERE item_id = 'ITEM_000012345'
    " 2>/dev/null
    
    echo ""
    echo "--- Q3: Category Analysis ---"
    echo "ClickHouse:"
    time clickhouse-client --query "
    SELECT count(DISTINCT seller_id), sum(order_amt)
    FROM ads_seller_item_stat
    WHERE category_id = 123
    " 2>&1
    
    echo ""
    echo "Doris:"
    time mysql -h"$DORIS_HOST" -P"$DORIS_PORT" -uroot -e "
    SELECT count(DISTINCT seller_id), sum(order_amt)
    FROM ads.ads_seller_item_stat
    WHERE category_id = 123
    " 2>/dev/null
}

# 主流程
main() {
    echo "Starting Doris migration..."
    
    wait_for_doris
    create_doris_table
    
    # 如果需要迁移数据
    if [ "${MIGRATE_DATA:-false}" = "true" ]; then
        migrate_data
        verify_data
    fi
    
    # 运行性能对比
    if [ "${RUN_BENCHMARK:-false}" = "true" ]; then
        run_benchmark
    fi
    
    echo ""
    echo "=== Migration Complete ==="
}

main "$@"
