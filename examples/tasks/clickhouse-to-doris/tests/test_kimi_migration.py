#!/usr/bin/env python3
"""
Test Kimi's ability to generate optimized Doris schema.
Uses shared kimi_client (KIMI_API_KEY / KIMI_URL / KIMI_MODEL).
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from kimi_client import call_kimi, KIMI_MODEL

CLICKHOUSE_SCHEMA = """
CREATE TABLE ads_seller_item_stat
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
"""

CLICKHOUSE_QUERIES = """
-- Q1: seller dashboard (high frequency)
SELECT seller_id, sum(imp_cnt), sum(clk_cnt), sum(order_cnt), sum(order_amt)
FROM ads_seller_item_stat
WHERE p_date BETWEEN '2025-04-16' AND '2025-04-22'
  AND seller_id = 'S_10012'
GROUP BY seller_id;

-- Q2: item trend (medium frequency)
SELECT p_date, sum(imp_cnt), sum(order_amt)
FROM ads_seller_item_stat
WHERE item_id = 'ITEM_100000'
  AND p_date BETWEEN '2025-04-01' AND '2025-04-22'
GROUP BY p_date ORDER BY p_date;

-- Q3: category analysis (low frequency)
SELECT seller_id, sum(order_amt) as gmv
FROM ads_seller_item_stat
WHERE category_id = 50
GROUP BY seller_id
ORDER BY gmv DESC LIMIT 10;
"""

PROMPT = f"""You are migrating a ClickHouse table to Apache Doris 2.1+.

## ClickHouse Source Table

```sql
{CLICKHOUSE_SCHEMA}
```

## Query Patterns

```sql
{CLICKHOUSE_QUERIES}
```

## Requirements

1. Create Doris table with DUPLICATE KEY model
2. Optimize for the three query patterns
3. Use appropriate indexes (Inverted Index, Bloom Filter)
4. Consider using ROLLUP for query optimization
5. Ensure SQL queries work with minimal modifications

## Key Constraints

- Doris prefix index has 36-byte limit for string columns
- seller_id is VARCHAR(32) (~21 bytes with prefix)
- item_id is VARCHAR(64) - cannot fit fully in prefix
- category_id is INT - needs alternative indexing

Output the complete Doris schema and queries:"""


def main():
    print(f"Testing Kimi: ClickHouse to Doris Migration ({KIMI_MODEL})")
    start = time.time()
    content = call_kimi([{"role": "user", "content": PROMPT}], temperature=0.3)
    elapsed = time.time() - start
    print(f"Response: {elapsed:.1f}s, {len(content)} chars\n")

    checks = {
        "DUPLICATE KEY": "DUPLICATE KEY" in content.upper(),
        "seller_id before p_date in key": (
            content.find("seller_id") < content.find("p_date")
            if "seller_id" in content and "p_date" in content else False
        ),
        "INVERTED INDEX for item_id": "INVERTED" in content.upper() and "item_id" in content.lower(),
        "ROLLUP for category": "ROLLUP" in content.upper() and "category" in content.lower(),
        "Bloom Filter": "bloom" in content.lower(),
    }

    score = sum(checks.values()) / len(checks) * 100
    print("=== Checks ===")
    for check, passed in checks.items():
        print(f"{'✓' if passed else '✗'} {check}")
    print(f"\nScore: {score:.0f}%")

    result = {
        "model": KIMI_MODEL,
        "elapsed_sec": round(elapsed, 1),
        "score": score,
        "checks": checks,
        "response": content,
    }
    out = Path(__file__).parent.parent / "results"
    out.mkdir(exist_ok=True)
    (out / "kimi_migration_test.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nSaved to {out}/")


if __name__ == "__main__":
    main()
