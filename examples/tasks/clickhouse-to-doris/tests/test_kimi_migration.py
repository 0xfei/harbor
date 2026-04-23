#!/usr/bin/env python3
"""
Test kimi-k2.5's ability to generate optimized Doris schema
"""

import os
import subprocess
import requests
import json
import tempfile

API_KEY = os.environ.get("BAILIAN_API_KEY", "")
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "kimi-k2.5"

# ClickHouse 原始表结构和查询
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
-- Q1: 卖家看板 (高频查询)
SELECT seller_id, sum(imp_cnt), sum(clk_cnt), sum(order_cnt), sum(order_amt)
FROM ads_seller_item_stat
WHERE p_date BETWEEN '2025-04-16' AND '2025-04-22'
  AND seller_id = 'S_10012'
GROUP BY seller_id;

-- Q2: 商品趋势 (中频查询)
SELECT p_date, sum(imp_cnt), sum(order_amt)
FROM ads_seller_item_stat
WHERE item_id = 'ITEM_100000'
  AND p_date BETWEEN '2025-04-01' AND '2025-04-22'
GROUP BY p_date ORDER BY p_date;

-- Q3: 品类分析 (低频查询)
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

## Output Format

1. Doris CREATE TABLE statement with all optimizations
2. Any necessary ROLLUP statements
3. Modified queries if needed
4. Explanation of optimization choices

Output the complete Doris schema and queries:
"""

def test_kimi_doris_migration():
    """Test kimi-k2.5's Doris migration capability"""
    
    print("=== Testing kimi-k2.5 Doris Migration ===\n")
    
    try:
        response = requests.post(
            f"{BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": PROMPT}],
                "temperature": 0.3,
                "max_tokens": 4096
            },
            timeout=180
        )
        
        content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        
        print("Response:")
        print("=" * 60)
        print(content[:3000])
        print("=" * 60)
        
        # 检查关键优化点
        print("\n=== Checking Optimization Points ===")
        
        checks = {
            "DUPLICATE KEY": "DUPLICATE KEY" in content.upper(),
            "seller_id first in Key": content.find("seller_id") < content.find("p_date") if "seller_id" in content and "p_date" in content else False,
            "INVERTED INDEX for item_id": "INVERTED" in content.upper() and "item_id" in content.lower(),
            "ROLLUP for category": "ROLLUP" in content.upper() and "category" in content.lower(),
            "Bloom Filter": "bloom" in content.lower(),
        }
        
        for check, passed in checks.items():
            status = "✅" if passed else "❌"
            print(f"{status} {check}")
        
        # 评分
        score = sum(checks.values()) / len(checks) * 100
        print(f"\n=== Score: {score:.0f}% ===")
        
        if score >= 80:
            print("✅ Excellent! kimi-k2.5 correctly designed Doris schema")
        elif score >= 60:
            print("⚠️  Partial success. Some optimizations missing")
        else:
            print("❌ Failed. Major issues in schema design")
        
        return {
            "model": MODEL,
            "score": score,
            "checks": checks,
            "response_length": len(content)
        }
        
    except Exception as e:
        print(f"Error: {e}")
        return {"error": str(e)}

def evaluate_schema_correctness():
    """Evaluate the correctness of generated schema"""
    
    print("\n=== Expected Schema Features ===")
    print("""
    1. DUPLICATE KEY(seller_id, p_date) - seller_id first for Q1
    2. INDEX idx_item_id (item_id) USING INVERTED - for Q2
    3. ADD ROLLUP r_category (category_id, ...) - for Q3
    4. PARTITION BY RANGE(p_date) - same as CH
    5. DISTRIBUTED BY HASH(seller_id) - even distribution
    """)
    
    print("\n=== Key Differences from ClickHouse ===")
    print("""
    ClickHouse: ORDER BY (p_date, seller_id, item_id, category_id)
    Doris Opt:  DUPLICATE KEY(seller_id, p_date) + INDEX + ROLLUP
    
    Reason: Doris prefix index limited to 36 bytes
    - Original: p_date(3) + seller_id(21) + item_id(前12) = 36 (耗尽)
    - Optimized: seller_id(21) + p_date(3) = 24 (完整)
    """)

if __name__ == "__main__":
    result = test_kimi_doris_migration()
    evaluate_schema_correctness()
    
    # 保存结果
    with open("/tmp/kimi_doris_test_result.json", "w") as f:
        json.dump(result, f, indent=2)
    
    print("\n=== Result saved to /tmp/kimi_doris_test_result.json ===")
