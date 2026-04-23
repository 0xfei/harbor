-- ClickHouse 优化版表结构
-- 核心决策：ORDER BY (seller_id, item_id) - 去掉 p_date（已是分区键）
-- 前缀索引字节分析：
--   seller_id: 10 chars → 10+1 = 11 bytes
--   item_id:   14 chars → 14+1 = 15 bytes
--   合计 26 bytes，小于 36 字节限制

DROP TABLE IF EXISTS ads_seller_item_stat;

CREATE TABLE ads_seller_item_stat (
    p_date        Date,
    seller_id     String,          -- S_00001234 (10 chars)
    item_id       String,          -- ITEM_000012345 (14 chars)
    category_id   Int32,
    sub_cat_name  String,
    imp_cnt       UInt64,
    clk_cnt       UInt64,
    order_cnt     UInt32,
    order_amt     Float64,
    refund_cnt    UInt32,
    refund_amt    Float64,

    -- INDEX 定义
    -- Q2: item_id bloom_filter FPR 2.5%，跳过 ~97% granules
    INDEX idx_item_id   item_id     TYPE bloom_filter(0.025) GRANULARITY 1,
    
    -- Q3: category_id set(512)，精确匹配跳过 ~70% granules  
    INDEX idx_category  category_id TYPE set(512)           GRANULARITY 1
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(p_date)
ORDER BY (seller_id, item_id)
SETTINGS index_granularity = 8192;

-- 三条测试查询

-- Q1: 卖家7日看板（高频查询）
-- 索引路径: ORDER BY 首列 seller_id → sparse index 精准 1 granule
SELECT seller_id,
       sum(imp_cnt) AS total_imp, 
       sum(clk_cnt) AS total_clk,
       sum(order_cnt) AS total_orders, 
       round(sum(order_amt), 2) AS total_gmv,
       round(sum(clk_cnt)/nullIf(sum(imp_cnt), 0)*100, 4) AS ctr,
       round(sum(order_cnt)/nullIf(sum(clk_cnt), 0)*100, 4) AS cvr
FROM ads_seller_item_stat
WHERE seller_id = 'S_00001234'
  AND p_date BETWEEN '2025-04-16' AND '2025-04-22'
GROUP BY seller_id;

-- Q2: 商品跨月趋势（中频查询）
-- 索引路径: bloom_filter(item_id) FPR 2.5%，~97% granules 跳过
SELECT p_date, seller_id, category_id,
       imp_cnt, clk_cnt, order_cnt, round(order_amt, 2) AS order_amt,
       round(clk_cnt/nullIf(imp_cnt, 0)*100, 4) AS ctr,
       round(order_cnt/nullIf(clk_cnt, 0)*100, 4) AS cvr,
       round(order_amt/nullIf(order_cnt, 0), 2) AS avg_price
FROM ads_seller_item_stat
WHERE item_id = 'ITEM_000012345'
  AND p_date BETWEEN '2025-01-01' AND '2025-04-22'
ORDER BY p_date;

-- Q3: 品类竞争力分析（低频查询）
-- 索引路径: set(512)(category_id) 精确匹配，~70% granules 跳过
SELECT seller_id,
       count(DISTINCT item_id) AS active_items,
       round(sum(order_amt), 2) AS gmv,
       sum(order_cnt) AS orders,
       round(sum(order_amt)/nullIf(count(DISTINCT item_id), 0), 2) AS gmv_per_item,
       round(sum(clk_cnt)/nullIf(sum(imp_cnt), 0)*100, 4) AS avg_ctr,
       round(sum(order_cnt)/nullIf(sum(clk_cnt), 0)*100, 4) AS avg_cvr,
       round(sum(order_amt)/nullIf(sum(order_cnt), 0), 2) AS avg_price,
       rank() OVER (ORDER BY sum(order_amt) DESC) AS gmv_rank
FROM ads_seller_item_stat
WHERE category_id = 123
  AND p_date BETWEEN '2025-04-01' AND '2025-04-22'
GROUP BY seller_id
HAVING sum(order_amt) > 1000
ORDER BY gmv DESC 
LIMIT 100;
