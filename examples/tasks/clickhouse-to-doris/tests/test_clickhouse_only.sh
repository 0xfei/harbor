#!/bin/bash
# 本地 ClickHouse 测试脚本（不需要 Docker Compose）

set -e

echo "=== Step 1: Create ClickHouse Table ==="
clickhouse-client --multiquery << 'EOF'
CREATE DATABASE IF NOT EXISTS ads;

DROP TABLE IF EXISTS ads.seller_item_stat;

CREATE TABLE ads.seller_item_stat
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

echo "=== Step 2: Generate Test Data ==="
python3 << 'PYEOF'
import random
import string
from datetime import datetime, timedelta

random.seed(42)

START_DATE = datetime(2025, 1, 1)
NUM_SELLERS = 1000
NUM_CATEGORIES = 100
NUM_ITEMS_PER_SELLER = 10
NUM_DAYS = 112

def gen_seller_id(i):
    return f"S_{i:08d}"

def gen_item_id(i):
    return f"ITEM_{i:010d}"

sellers = [gen_seller_id(i) for i in range(1, NUM_SELLERS + 1)]
categories = list(range(1, NUM_CATEGORIES + 1))

# 生成 INSERT 数据
rows = []
for day_offset in range(NUM_DAYS):
    p_date = (START_DATE + timedelta(days=day_offset)).strftime('%Y-%m-%d')
    for seller in sellers:
        for item_idx in range(NUM_ITEMS_PER_SELLER):
            item_id = f"ITEM_{hash((seller, item_idx)) % 100000:010d}"
            cat_id = random.choice(categories)
            imp_cnt = random.randint(100, 10000)
            clk_cnt = max(0, int(imp_cnt * random.uniform(0.01, 0.15)))
            order_cnt = max(0, int(clk_cnt * random.uniform(0.01, 0.3)))
            order_amt = round(order_cnt * random.uniform(50, 500), 2)
            refund_cnt = max(0, int(order_cnt * random.uniform(0, 0.1)))
            refund_amt = round(refund_cnt * random.uniform(30, 300), 2)
            
            rows.append(f"('{p_date}', '{seller}', '{item_id}', {cat_id}, 'cat_{cat_id}', {imp_cnt}, {clk_cnt}, {order_cnt}, {order_amt}, {refund_cnt}, {refund_amt})")

# 批量插入
batch_size = 10000
total = 0
for i in range(0, len(rows), batch_size):
    batch = rows[i:i+batch_size]
    sql = "INSERT INTO ads.seller_item_stat VALUES\n" + ",\n".join(batch) + ";"
    print(f"Inserting batch {i//batch_size + 1}: {len(batch)} rows...")
    # 写入文件让 clickhouse-client 执行
    with open('/tmp/batch.sql', 'w') as f:
        f.write(sql)
    import subprocess
    subprocess.run(['clickhouse-client', '--multiquery', '-q', sql], check=True, capture_output=True)
    total += len(batch)

print(f"Total rows inserted: {total}")
PYEOF

echo "=== Step 3: Run ClickHouse Queries ==="
clickhouse-client --multiquery << 'EOF'
-- Q1: Seller Dashboard
SELECT 'Q1';
SELECT seller_id, sum(imp_cnt) AS total_imp, sum(clk_cnt) AS total_clk, sum(order_cnt) AS total_orders, sum(order_amt) AS total_gmv
FROM ads.seller_item_stat
WHERE p_date BETWEEN '2025-04-16' AND '2025-04-22'
  AND seller_id = 'S_00000123'
GROUP BY seller_id;

-- Q2: Item Trend
SELECT 'Q2';
SELECT count() FROM ads.seller_item_stat
WHERE item_id LIKE 'ITEM_%0001'
  AND p_date BETWEEN '2025-01-01' AND '2025-04-22';

-- Q3: Category Analysis
SELECT 'Q3';
SELECT count() FROM (
    SELECT seller_id, sum(order_amt) AS gmv
    FROM ads.seller_item_stat
    WHERE category_id = 50
      AND p_date BETWEEN '2025-04-01' AND '2025-04-22'
    GROUP BY seller_id
    HAVING gmv > 10000
);

-- Table Stats
SELECT 'Table Stats';
SELECT count() AS total_rows, uniqExact(seller_id) AS sellers, uniqExact(item_id) AS items FROM ads.seller_item_stat;
EOF

echo "=== ClickHouse Test Complete ==="
