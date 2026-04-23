-- ClickHouse 原始表结构
-- 用于生成基准数据和查询性能

CREATE DATABASE IF NOT EXISTS ads;

CREATE TABLE ads.seller_item_stat
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

    -- 跳数索引：弥补 item_id / category_id 不在前缀的问题
    INDEX idx_item_id   item_id     TYPE bloom_filter GRANULARITY 4,
    INDEX idx_category  category_id TYPE set(0)       GRANULARITY 4
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(p_date)
ORDER BY (p_date, seller_id, item_id, category_id)
SETTINGS index_granularity = 8192;
