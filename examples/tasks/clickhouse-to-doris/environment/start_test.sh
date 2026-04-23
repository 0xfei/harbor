#!/bin/bash
# 完整启动和测试脚本
set -e

echo "=== Starting ClickHouse Server ==="
clickhouse-server --config-file=/etc/clickhouse-server/config.xml --daemon

# 等待 ClickHouse 就绪
echo "Waiting for ClickHouse to be ready..."
for i in {1..30}; do
    if clickhouse-client --query "SELECT 1" >/dev/null 2>&1; then
        echo "ClickHouse is ready"
        break
    fi
    sleep 1
done

echo ""
echo "=== Creating ClickHouse Source Table ==="
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

echo ""
echo "=== Generating Test Data ==="
python3 /app/generate_data.py

echo ""
echo "=== Running ClickHouse Benchmark ==="
python3 -c "
import sys
sys.path.insert(0, '/app')
from benchmark import run_clickhouse_benchmark
results = run_clickhouse_benchmark()
print('ClickHouse Results:', results)
" 2>&1 | tee /logs/verifier/ch_benchmark.txt

echo ""
echo "=== Test Environment Ready ==="
echo "Connect with: clickhouse-client"
echo ""
echo "To test Doris optimization, connect to external Doris service"

# 保持容器运行
tail -f /dev/null
