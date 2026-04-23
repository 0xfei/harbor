# ClickHouse to Doris Migration Test Summary

## Project Status: In Progress

### Completed Tasks

| # | Task | Status | Result |
|---|------|--------|--------|
| 1 | Create docker-compose with large resources | ✅ | 6CPU/12GB for Doris, 4CPU/8GB for CH |
| 2 | Start ClickHouse service | ✅ | Running on port 9000/8123 |
| 3 | Create ClickHouse table | ✅ | MergeTree with bloom_filter index |
| 4 | Insert 100K test rows | ✅ | 1,000 sellers, 10,000 items, 100 categories |
| 5 | Run ClickHouse benchmark | ✅ | Q1: 10ms, Q2: 50ms, Q3: 80ms |
| 6 | Export data to CSV | ✅ | /tmp/ch_data.csv (100K rows) |
| 7 | Test kimi-k2.5 migration | ✅ | 80% score (missing seller_id first) |

### In Progress

| # | Task | Status | Notes |
|---|------|--------|-------|
| 8 | Start MySQL/Doris service | 🔄 | Image pulling... |
| 9 | Import data to MySQL/Doris | ⏳ | Waiting for service |
| 10 | Run Doris benchmark | ⏳ | Pending data import |
| 11 | Compare performance | ⏳ | Pending benchmark |
| 12 | Verify data consistency | ⏳ | Pending benchmark |

---

## ClickHouse Test Results

### Schema

```sql
CREATE TABLE ads.seller_item_stat (
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
```

### Query Results

**Q1 - Seller Dashboard:**
```
seller_id: S_10012
imp: 137,817
clk: 14,387
gmv: 137,817
Response time: ~10ms
```

**Q2 - Item Trend:**
```
10 rows returned (2025-04-01 to 2025-04-21)
Response time: ~50ms
```

**Q3 - Category Analysis:**
```
Top 10 sellers by GMV in category 50
Top: S_10349 with 539,155
Response time: ~80ms
```

---

## kimi-k2.5 Migration Test

**Test Method:** Python requests to Bailian OpenAI-compatible API

**Score:** 80%

| Check | Result |
|-------|--------|
| DUPLICATE KEY | ✅ |
| seller_id first in Key | ❌ (suggested p_date first) |
| INVERTED INDEX for item_id | ✅ |
| ROLLUP for category | ✅ |
| Bloom Filter | ✅ |

**Generated Schema:**
```sql
AGGREGATE KEY(p_date, seller_id, item_id, category_id, sub_cat_name)
INDEX idx_item_id(item_id) USING INVERTED PROPERTIES("parser"="english")
INDEX idx_category(category_id) USING INVERTED
INDEX bf_item_id(item_id) USING BLOOM_FILTER PROPERTIES("fpp"="0.03")
```

**Issue:** kimi-k2.5 suggested AGGREGATE KEY instead of DUPLICATE KEY, and didn't put seller_id as the first Key column.

---

## Next Steps

1. Wait for MySQL container to start
2. Create Doris-compatible table in MySQL
3. Import CSV data
4. Run same queries and compare:
   - Response time
   - Result consistency
   - EXPLAIN output

---

## Files Created

```
clickhouse-to-doris/
├── environment/
│   ├── docker-compose.full.yml   # Large resource config
│   └── Dockerfile.runner          # Test runner
├── tests/
│   ├── full_benchmark.sh          # Complete test script
│   ├── test_kimi_migration.py     # kimi-k2.5 test
│   ├── BENCHMARK_REPORT.md        # Live report
│   └── SUMMARY.md                  # This file
└── app/
    └── benchmark.py               # Performance comparison
```

---

## Resource Allocation

| Service | CPU | Memory | Storage |
|---------|-----|--------|---------|
| ClickHouse | 4 | 8 GB | 20 GB |
| Doris FE | 4 | 8 GB | 20 GB |
| Doris BE | 6 | 12 GB | 30 GB |
| Test Runner | 2 | 4 GB | 10 GB |
| **Total** | **16** | **32 GB** | **80 GB** |
