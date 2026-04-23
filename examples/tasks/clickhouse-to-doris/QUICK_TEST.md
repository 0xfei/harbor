# ClickHouse to Doris Migration - 快速测试指南

## 方式 1：仅 ClickHouse 基准测试（最快）

```bash
# 启动 ClickHouse 容器
docker run -d --name ch-quick-test clickhouse/clickhouse-server:24.3

# 等待启动
sleep 10

# 创建表并插入数据
docker exec ch-quick-test clickhouse-client --multiquery << 'EOF'
CREATE DATABASE IF NOT EXISTS ads;

CREATE TABLE ads.seller_item_stat (
    p_date Date,
    seller_id String,
    item_id String,
    category_id Int32,
    sub_cat_name String,
    imp_cnt UInt64,
    clk_cnt UInt64,
    order_cnt UInt32,
    order_amt Float64,
    refund_cnt UInt32,
    refund_amt Float64
)
ENGINE = MergeTree()
ORDER BY (p_date, seller_id, item_id);

-- 插入测试数据
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
FROM numbers(100000);
EOF

# 验证数据
docker exec ch-quick-test clickhouse-client --query "
SELECT count() as rows, 
       uniqExact(seller_id) as sellers,
       uniqExact(item_id) as items
FROM ads.seller_item_stat
"

# 运行查询
docker exec ch-quick-test clickhouse-client --multiquery << 'EOF'
-- Q1: 卖家看板
SELECT seller_id, sum(imp_cnt) as imp, sum(clk_cnt) as clk, sum(order_amt) as gmv
FROM ads.seller_item_stat
WHERE p_date BETWEEN '2025-04-16' AND '2025-04-22'
  AND seller_id = 'S_10012'
GROUP BY seller_id;

-- Q2: 商品趋势
SELECT p_date, sum(imp_cnt) as imp, sum(order_amt) as gmv
FROM ads.seller_item_stat
WHERE item_id = 'ITEM_100000'
GROUP BY p_date ORDER BY p_date;

-- Q3: 品类分析
SELECT seller_id, sum(order_amt) as gmv, count(DISTINCT item_id) as items
FROM ads.seller_item_stat
WHERE category_id = 50
GROUP BY seller_id
ORDER BY gmv DESC LIMIT 10;
EOF

# 清理
docker stop ch-quick-test && docker rm ch-quick-test
```

## 方式 2：完整 Harbor 测试

```bash
cd /Users/0x01f/harbor

# 构建测试镜像（需要 Python 和 MySQL 客户端）
docker build -t clickhouse-to-doris:latest \
  -f examples/tasks/clickhouse-to-doris/environment/Dockerfile \
  examples/tasks/clickhouse-to-doris/environment/

# Harbor 运行（需要外部 Doris 服务）
uv run harbor run -a oracle -p examples/tasks/clickhouse-to-doris
```

## 预期结果

| 测试项 | ClickHouse 结果 | Doris 优化目标 |
|--------|------------------|----------------|
| 表创建 | ✅ 成功 | ✅ 成功 |
| 数据量 | 100K 行 | 100K 行 |
| Q1 响应 | <50ms | <50ms (Key 命中) |
| Q2 响应 | <100ms | <80ms (倒排索引) |
| Q3 响应 | <200ms | <150ms (ROLLUP) |

## 关键验证点

1. **Key 顺序**: Doris DUPLICATE KEY 应为 `(seller_id, p_date)`
2. **倒排索引**: `idx_item_id` 必须存在且类型为 INVERTED
3. **ROLLUP**: `r_category` 应包含 category_id 作为首列
4. **数据一致性**: CH 和 Doris 查询结果必须完全一致
