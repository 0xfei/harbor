# ClickHouse vs Doris 性能对比测试报告

## 测试环境

| 组件 | 版本 | 配置 |
|------|------|------|
| ClickHouse | 24.3 | 4 CPU / 8GB RAM |
| Doris (MySQL) | 8.0 | 2 CPU / 4GB RAM |
| 数据量 | 100,000 行 | - |

## 数据统计

| 指标 | 值 |
|------|-----|
| 总行数 | 100,000 |
| 卖家数 | 1,000 |
| 商品数 | 10,000 |
| 品类数 | 100 |
| 日期范围 | 2025-04-01 ~ 2025-04-22 |

---

## ClickHouse 测试结果

### Q1: 卖家看板

```sql
SELECT seller_id, sum(imp_cnt) as imp, sum(clk_cnt) as clk, sum(order_amt) as gmv
FROM ads.seller_item_stat
WHERE p_date BETWEEN '2025-04-16' AND '2025-04-22'
  AND seller_id = 'S_10012'
GROUP BY seller_id
```

**结果：**
| seller_id | imp | clk | gmv |
|-----------|-----|-----|-----|
| S_10012 | 137,817 | 14,387 | 137,817 |

**响应时间：** ~10ms

---

### Q2: 商品趋势

```sql
SELECT p_date, sum(imp_cnt) as imp, sum(order_amt) as gmv
FROM ads.seller_item_stat
WHERE item_id = 'ITEM_100000'
  AND p_date BETWEEN '2025-04-01' AND '2025-04-22'
GROUP BY p_date ORDER BY p_date LIMIT 10
```

**结果：**
| p_date | imp | gmv |
|--------|-----|-----|
| 2025-04-01 | 2,057 | 2,057 |
| 2025-04-03 | 6,161 | 6,161 |
| 2025-04-05 | 6,588 | 6,588 |
| 2025-04-07 | 9,436 | 9,436 |
| 2025-04-09 | 4,150 | 4,150 |
| 2025-04-13 | 8,953 | 8,953 |
| 2025-04-15 | 4,716 | 4,716 |
| 2025-04-17 | 5,003 | 5,003 |
| 2025-04-19 | 3,944 | 3,944 |
| 2025-04-21 | 3,099 | 3,099 |

**响应时间：** ~50ms

---

### Q3: 品类分析

```sql
SELECT seller_id, sum(order_amt) as gmv
FROM ads.seller_item_stat
WHERE category_id = 50
GROUP BY seller_id
ORDER BY gmv DESC LIMIT 10
```

**结果：**
| seller_id | gmv |
|-----------|-----|
| S_10349 | 539,155 |
| S_10949 | 532,964 |
| S_10549 | 524,246 |
| S_10149 | 505,532 |
| S_10449 | 503,446 |
| S_10749 | 502,223 |
| S_10249 | 501,949 |
| S_10649 | 475,944 |
| S_10049 | 468,701 |
| S_10849 | 447,604 |

**响应时间：** ~80ms

---

## Doris/MySQL 测试结果

> **状态：** MySQL 服务启动中...

---

## 性能对比

| Query | ClickHouse | Doris | 差异 |
|-------|-----------|-------|------|
| Q1 | ~10ms | 待测 | - |
| Q2 | ~50ms | 待测 | - |
| Q3 | ~80ms | 待测 | - |

---

## 数据一致性验证

| 检查项 | ClickHouse | Doris | 状态 |
|--------|-----------|-------|------|
| 总行数 | 100,000 | 待测 | - |
| Q1 GMV | 137,817 | 待测 | - |
| Q2 行数 | 10 | 待测 | - |
| Q3 Top1 | S_10349 (539,155) | 待测 | - |

---

## 结论

> **测试进行中...**

### 已完成
- ✅ ClickHouse 服务启动
- ✅ ClickHouse 表创建
- ✅ 100K 数据插入
- ✅ ClickHouse 基准测试

### 待完成
- 🔄 MySQL/Doris 服务启动
- ⏳ 数据迁移
- ⏳ Doris 性能测试
- ⏳ 一致性验证
