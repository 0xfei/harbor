-- Query 1: 卖家近7日经营看板
-- 测试：seller_id 精确匹配 + p_date 范围过滤 + 聚合
SELECT
    seller_id,
    sum(imp_cnt)                                                   AS total_imp,
    sum(clk_cnt)                                                   AS total_clk,
    sum(order_cnt)                                                 AS total_orders,
    sum(order_amt)                                                 AS total_gmv,
    round(sum(clk_cnt)   / nullIf(sum(imp_cnt),  0) * 100, 4)    AS ctr,
    round(sum(order_cnt) / nullIf(sum(clk_cnt),  0) * 100, 4)    AS cvr
FROM ads.seller_item_stat
WHERE p_date   BETWEEN '2025-04-16' AND '2025-04-22'
  AND seller_id = 'S_00000123'
GROUP BY seller_id;

-- Query 2: 商品跨月趋势
-- 测试：item_id 精确匹配（非排序列，依赖 bloom_filter）+ 时间范围
SELECT
    p_date,
    seller_id,
    category_id,
    imp_cnt, clk_cnt, order_cnt, order_amt,
    round(clk_cnt   / nullIf(imp_cnt,  0) * 100, 4)  AS ctr,
    round(order_cnt / nullIf(clk_cnt,  0) * 100, 4)  AS cvr,
    round(order_amt / nullIf(order_cnt, 0), 2)         AS avg_order_price
FROM ads.seller_item_stat
WHERE item_id = 'ITEM_0000000001'
  AND p_date BETWEEN '2025-01-01' AND '2025-04-22'
ORDER BY p_date;

-- Query 3: 品类竞争力分析
-- 测试：category_id 精确匹配（非排序列，依赖 set 索引）+ 窗口函数
SELECT
    seller_id,
    count(DISTINCT item_id)                                        AS active_items,
    sum(order_amt)                                                 AS gmv,
    sum(order_cnt)                                                 AS orders,
    round(sum(order_amt) / nullIf(count(DISTINCT item_id), 0), 2) AS gmv_per_item,
    round(sum(clk_cnt)   / nullIf(sum(imp_cnt),  0) * 100, 4)    AS avg_ctr,
    round(sum(order_cnt) / nullIf(sum(clk_cnt),  0) * 100, 4)    AS avg_cvr,
    round(sum(order_amt) / nullIf(sum(order_cnt), 0), 2)          AS avg_order_price,
    rank() OVER (ORDER BY sum(order_amt) DESC)                    AS gmv_rank
FROM ads.seller_item_stat
WHERE category_id = 50
  AND p_date BETWEEN '2025-04-01' AND '2025-04-22'
GROUP BY seller_id
HAVING gmv > 10000
ORDER BY gmv DESC
LIMIT 100;
