# ClickHouse to Doris Migration Task

| 属性 | 值 |
|------|----|
| **难度** | Hard |
| **类别** | 数据库迁移 / SQL 优化 |
| **编程语言** | SQL, Python |
| **容器资源** | 6 CPU / 12 GB RAM |
| **Agent 超时** | 3600 秒 (1小时) |
| **Verifier 超时** | 600 秒 |
| **最大尝试次数** | 5 次 |

---

## 任务描述

将 ClickHouse 的 `ads_seller_item_stat` 表迁移到 Apache Doris，要求：
1. 保持查询语义一致
2. 充分利用 Doris 的索引机制（前缀索引、倒排索引、ROLLUP）
3. SQL 修改量最小化
4. 性能接近或优于 ClickHouse

**关键挑战：**
- Doris 前缀索引仅支持 Key 列，最多 36 字节
- ClickHouse 的 `ORDER BY` 和 `INDEX` 机制与 Doris 不同
- 一张表难以同时优化 3 种不同维度的过滤查询

---

## ClickHouse 原始表结构

```sql
CREATE TABLE ads_seller_item_stat
(
    p_date        Date,
    seller_id     String,         -- 10字符
    item_id       String,         -- 14字符
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

---

## 三条查询及优化目标

### Query 1: 卖家看板（高频）
```sql
WHERE p_date BETWEEN ... AND seller_id = 'S_00000123'
```
**优化目标：** 前缀索引直接命中 seller_id

### Query 2: 商品趋势（中频）
```sql
WHERE item_id = 'ITEM_0000000001' AND p_date BETWEEN ...
```
**优化目标：** 倒排索引行级定位

### Query 3: 品类分析（低频）
```sql
WHERE category_id = 50 AND p_date BETWEEN ... GROUP BY seller_id
```
**优化目标：** ROLLUP 自动路由

---

## 测试验证

### 验证项目
| # | 测试项 | 说明 |
|---|--------|------|
| 1 | Table exists | Doris 表已创建 |
| 2 | Key order | Key 列顺序正确 (seller_id, p_date) |
| 3 | Indexes | 倒排索引存在 |
| 4 | Data count | 数据行数一致 |
| 5 | Q1 results | 聚合结果一致 |
| 6 | Q2 results | 有序明细一致 |
| 7 | Q3 results | 窗口函数结果一致 |

### 性能基准
```bash
python3 /app/benchmark.py
```
输出对比：
- ClickHouse 平均响应时间
- Doris 平均响应时间
- 加速比

---

## ClickHouse 实测结果

### 测试环境
- **镜像**: `clickhouse/clickhouse-server:24.3`
- **数据量**: 100,000 行
- **分区**: 2025-04-01 ~ 2025-04-22 (22 天)
- **卖家数**: 1,000
- **商品数**: 10,000
- **品类数**: 100

### 查询性能

| Query | 响应时间 | 结果 |
|-------|---------|------|
| Q1 卖家看板 | ~10ms | S_10012 \| imp: 137,817 \| clk: 14,387 \| gmv: 137,817 |
| Q2 商品趋势 | ~50ms | 10 行日期明细 |
| Q3 品类分析 | ~80ms | Top 10 GMV 卖家 |

### Top 10 卖家（Q3 结果）

| 排名 | 卖家 | GMV |
|------|------|-----|
| 1 | S_10349 | 539,155 |
| 2 | S_10949 | 532,964 |
| 3 | S_10549 | 524,246 |
| 4 | S_10149 | 505,532 |
| 5 | S_10449 | 503,446 |
| 6 | S_10749 | 502,223 |
| 7 | S_10249 | 501,949 |
| 8 | S_10649 | 475,944 |
| 9 | S_10049 | 468,701 |
| 10 | S_10849 | 447,604 |

---

## kimi-k2.5 测试结果

**测试方法**: Python requests 调用 Bailian OpenAI-compatible API

**评分**: **80%** ✅ 优秀

| 检查项 | 状态 |
|--------|------|
| DUPLICATE KEY | ✅ 正确 |
| seller_id 首列 | ❌ 建议改进 |
| INVERTED INDEX for item_id | ✅ 正确 |
| ROLLUP for category | ✅ 正确 |
| Bloom Filter | ✅ 正确 |

**生成方案示例**:
```sql
AGGREGATE KEY(p_date, seller_id, item_id, category_id, sub_cat_name)
INDEX idx_item_id(item_id) USING INVERTED PROPERTIES("parser"="english")
INDEX idx_category(category_id) USING INVERTED
INDEX bf_item_id(item_id) USING BLOOM_FILTER PROPERTIES("fpp"="0.03")
```

**改进建议**: kimi-k2.5 应将 `seller_id` 放在 Key 列首位，以优化 Q1 查询性能。

---

## 待完成测试

- [ ] MySQL/Doris 服务启动
- [ ] 数据迁移
- [ ] Doris 性能测试
- [ ] 结果一致性对比
- 结果一致性验证

---

## 预期结果

| Agent | 结果 | 说明 |
|-------|------|------|
| **oracle** | 所有测试通过 | 正确设计 Key + Index + ROLLUP |
| **nop** | 表不存在 | 需 Agent 创建表结构 |
| **kimi-k2.5** | 预期 < 50% | 需理解 Doris 前缀索引机制 |

---

## 文件结构

```
clickhouse-to-doris/
├── task.toml           # Harbor 配置
├── instruction.md      # Agent 可见的任务说明
├── TASK.md             # 本文件
├── environment/
│   ├── Dockerfile      # 测试容器
│   └── docker-compose.yml  # 完整环境编排
├── tests/
│   ├── test.sh         # Verifier 入口
│   ├── verify_migration.py  # 结果一致性验证
│   └── run_local_test.sh    # 本地测试脚本
├── solution/
│   └── solve.sh        # Oracle 完整方案
└── app/
    ├── clickhouse_schema.sql
    ├── clickhouse_queries.sql
    ├── generate_data.py
    └── benchmark.py    # 性能对比脚本
```
