# ClickHouse to Doris Migration Task

## Background

You are migrating an analytics workload from ClickHouse to Apache Doris. The original ClickHouse table stores seller item statistics for an e-commerce platform, and you need to create an equivalent Doris table that can efficiently serve the same queries.

## ClickHouse Source Table

```sql
CREATE TABLE ads_seller_item_stat
(
    p_date        Date,
    seller_id     String,         -- e.g. "S_00012345"（10字符）
    item_id       String,         -- e.g. "ITEM_000987654"（14字符）
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
```

## Query Patterns

### Query 1: Seller Dashboard (High Frequency)
```sql
SELECT seller_id, sum(imp_cnt), sum(clk_cnt), sum(order_cnt), sum(order_amt),
       round(sum(clk_cnt)/nullIf(sum(imp_cnt),0)*100,4) AS ctr,
       round(sum(order_cnt)/nullIf(sum(clk_cnt),0)*100,4) AS cvr
FROM ads_seller_item_stat
WHERE p_date BETWEEN '2025-04-16' AND '2025-04-22'
  AND seller_id = 'S_00000123'
GROUP BY seller_id;
```

### Query 2: Item Trend Analysis (Medium Frequency)
```sql
SELECT p_date, seller_id, category_id, imp_cnt, clk_cnt, order_cnt, order_amt
FROM ads_seller_item_stat
WHERE item_id = 'ITEM_0000000001'
  AND p_date BETWEEN '2025-01-01' AND '2025-04-22'
ORDER BY p_date;
```

### Query 3: Category Analysis (Low Frequency)
```sql
SELECT seller_id, count(DISTINCT item_id) AS active_items,
       sum(order_amt) AS gmv, rank() OVER (ORDER BY sum(order_amt) DESC) AS gmv_rank
FROM ads_seller_item_stat
WHERE category_id = 50
  AND p_date BETWEEN '2025-04-01' AND '2025-04-22'
GROUP BY seller_id
HAVING gmv > 10000
ORDER BY gmv DESC LIMIT 100;
```

## Requirements

1. **Create Doris Table**: Design a Doris table schema that can efficiently serve all three query patterns
2. **Generate Test Data**: Create Python script to generate ~100K rows of test data
3. **Migrate Queries**: Ensure the three queries work correctly in Doris with minimal modifications
4. **Verify Performance**: Compare query execution time between ClickHouse baseline and Doris

## Constraints

- Doris version: 2.1.0+
- Single-node deployment (no distributed cluster)
- Total data size: ~100K rows (scaled down for testing)
- SQL changes should be minimal (prefer identical SQL where possible)

## Hints

- Doris uses different indexing mechanisms than ClickHouse
- Consider how Doris handles the `ORDER BY` vs `DUPLICATE KEY` semantics
- Doris has a 36-byte prefix index limit for string columns
- Inverted indexes and ROLLUP are available in Doris 2.1+

## Deliverables

1. Doris CREATE TABLE statement
2. Data generation Python script
3. Doris-compatible query statements
4. Performance comparison report
