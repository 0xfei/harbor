#!/usr/bin/env python3
"""简化版 ClickHouse Benchmark"""

import subprocess
import time
import json

def run_query(query):
    """运行 ClickHouse 查询"""
    start = time.time()
    result = subprocess.run(
        ["clickhouse-client", "--query", query],
        capture_output=True,
        text=True,
        timeout=60
    )
    elapsed = time.time() - start
    return result.stdout.strip(), elapsed, result.returncode

def main():
    queries = {
        "Q1": """
        SELECT seller_id, sum(imp_cnt), sum(clk_cnt), sum(order_cnt), sum(order_amt)
        FROM ads.seller_item_stat
        WHERE p_date BETWEEN '2025-04-16' AND '2025-04-22'
          AND seller_id = 'S_00000123'
        GROUP BY seller_id
        """,
        "Q2": """
        SELECT p_date, seller_id, category_id, imp_cnt, clk_cnt, order_cnt
        FROM ads.seller_item_stat
        WHERE item_id = 'ITEM_0000000001'
          AND p_date BETWEEN '2025-01-01' AND '2025-04-22'
        ORDER BY p_date
        """,
        "Q3": """
        SELECT seller_id, sum(order_amt) AS gmv, count(DISTINCT item_id) AS items
        FROM ads.seller_item_stat
        WHERE category_id = 50
          AND p_date BETWEEN '2025-04-01' AND '2025-04-22'
        GROUP BY seller_id
        ORDER BY gmv DESC
        LIMIT 100
        """
    }
    
    results = {}
    
    print("=" * 60)
    print("ClickHouse Benchmark")
    print("=" * 60)
    
    for name, query in queries.items():
        print(f"\n{name}:")
        times = []
        for i in range(5):
            output, elapsed, code = run_query(query)
            times.append(elapsed)
            if i == 0:
                rows = len(output.split('\n')) if output else 0
        
        avg_time = sum(times) / len(times)
        results[name] = {"avg_time": round(avg_time, 4), "rows": rows}
        print(f"  Rows: {rows}")
        print(f"  Avg Time: {avg_time:.4f}s")
    
    # 保存结果
    with open("/logs/verifier/ch_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print("\n" + "=" * 60)
    print("Results saved to /logs/verifier/ch_results.json")

if __name__ == "__main__":
    main()
