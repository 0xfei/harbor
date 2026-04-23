#!/usr/bin/env python3
"""
Verify Doris migration correctness
- Check table structure matches expectations
- Verify query results consistency with ClickHouse
"""

import subprocess
import sys
import json

def run_ch(query):
    """Run ClickHouse query."""
    result = subprocess.run(
        ["clickhouse-client", "--host", "clickhouse", "--query", query],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        raise RuntimeError(f"CH Error: {result.stderr}")
    return result.stdout.strip().split('\n') if result.stdout.strip() else []

def run_doris(query):
    """Run Doris query via MySQL."""
    result = subprocess.run(
        ["mysql", "-hdoris-fe", "-P9030", "-uroot", "-N", "-e", query],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        raise RuntimeError(f"Doris Error: {result.stderr}")
    return result.stdout.strip().split('\n') if result.stdout.strip() else []

def test_table_exists():
    """Verify Doris table exists with correct structure."""
    result = run_doris("SHOW CREATE TABLE ads.seller_item_stat")
    create_stmt = '\n'.join(result)
    
    assert "seller_id" in create_stmt, "Missing seller_id column"
    assert "p_date" in create_stmt, "Missing p_date column"
    assert "item_id" in create_stmt, "Missing item_id column"
    assert "category_id" in create_stmt, "Missing category_id column"
    assert "DUPLICATE KEY" in create_stmt.upper(), "Must use DUPLICATE KEY model"
    print("✅ Table structure verified")

def test_key_order():
    """Verify Key columns are in optimal order for Q1."""
    result = run_doris("SHOW CREATE TABLE ads.seller_item_stat")
    create_stmt = '\n'.join(result)
    
    # Check that seller_id comes before p_date in Key
    lines = create_stmt.split('\n')
    key_line = [l for l in lines if 'DUPLICATE KEY' in l.upper() or 'KEY' in l]
    if key_line:
        key_part = key_line[0]
        # seller_id should be first
        assert key_part.find('seller_id') < key_part.find('p_date'), \
            "Key order should be (seller_id, p_date) for Q1 optimization"
    print("✅ Key order verified")

def test_indexes():
    """Verify inverted indexes exist for non-Key filtering."""
    result = run_doris("SHOW CREATE TABLE ads.seller_item_stat")
    create_stmt = '\n'.join(result).upper()
    
    # Should have index for item_id (Q2 optimization)
    assert "INDEX" in create_stmt and "ITEM_ID" in create_stmt, \
        "Missing index for item_id (Q2 optimization)"
    print("✅ Indexes verified")

def test_data_count():
    """Verify data migrated correctly."""
    ch_count = run_ch("SELECT count() FROM ads.seller_item_stat")[0]
    doris_count = run_doris("SELECT count(*) FROM ads.seller_item_stat")[0]
    
    assert ch_count == doris_count, f"Count mismatch: CH={ch_count}, Doris={doris_count}"
    print(f"✅ Data count verified: {ch_count} rows")

def test_q1_results():
    """Verify Q1 aggregation results match."""
    ch_q = """
    SELECT seller_id, sum(imp_cnt), sum(clk_cnt), sum(order_cnt), sum(order_amt)
    FROM ads.seller_item_stat
    WHERE p_date BETWEEN '2025-04-16' AND '2025-04-22'
      AND seller_id = 'S_00000123'
    GROUP BY seller_id
    """
    
    doris_q = """
    SELECT seller_id, sum(imp_cnt), sum(clk_cnt), sum(order_cnt), sum(order_amt)
    FROM ads.seller_item_stat
    WHERE p_date BETWEEN '2025-04-16' AND '2025-04-22'
      AND seller_id = 'S_00000123'
    GROUP BY seller_id
    """
    
    ch_result = run_ch(ch_q)
    doris_result = run_doris(doris_q)
    
    assert ch_result == doris_result, f"Q1 mismatch:\nCH: {ch_result}\nDoris: {doris_result}"
    print("✅ Q1 results verified")

def test_q2_order():
    """Verify Q2 ordered results match."""
    ch_q = """
    SELECT p_date, seller_id, category_id, imp_cnt, clk_cnt, order_cnt, order_amt
    FROM ads.seller_item_stat
    WHERE item_id = 'ITEM_0000000001'
      AND p_date BETWEEN '2025-01-01' AND '2025-04-22'
    ORDER BY p_date
    """
    
    doris_q = """
    SELECT p_date, seller_id, category_id, imp_cnt, clk_cnt, order_cnt, order_amt
    FROM ads.seller_item_stat
    WHERE item_id = 'ITEM_0000000001'
      AND p_date BETWEEN '2025-01-01' AND '2025-04-22'
    ORDER BY p_date
    """
    
    ch_result = run_ch(ch_q)
    doris_result = run_doris(doris_q)
    
    assert ch_result == doris_result, f"Q2 mismatch"
    print("✅ Q2 results verified")

def test_q3_aggregation():
    """Verify Q3 window function results."""
    ch_q = """
    SELECT seller_id, sum(order_amt) AS gmv, rank() OVER (ORDER BY sum(order_amt) DESC)
    FROM ads.seller_item_stat
    WHERE category_id = 50
      AND p_date BETWEEN '2025-04-01' AND '2025-04-22'
    GROUP BY seller_id
    HAVING gmv > 10000
    ORDER BY gmv DESC
    LIMIT 10
    """
    
    doris_q = """
    SELECT seller_id, sum(order_amt) AS gmv, rank() OVER (ORDER BY sum(order_amt) DESC)
    FROM ads.seller_item_stat
    WHERE category_id = 50
      AND p_date BETWEEN '2025-04-01' AND '2025-04-22'
    GROUP BY seller_id
    HAVING gmv > 10000
    ORDER BY gmv DESC
    LIMIT 10
    """
    
    ch_result = run_ch(ch_q)
    doris_result = run_doris(doris_q)
    
    assert ch_result == doris_result, f"Q3 mismatch"
    print("✅ Q3 results verified")

def main():
    tests = [
        ("Table exists", test_table_exists),
        ("Key order", test_key_order),
        ("Indexes", test_indexes),
        ("Data count", test_data_count),
        ("Q1 aggregation", test_q1_results),
        ("Q2 ordered results", test_q2_order),
        ("Q3 window function", test_q3_aggregation),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_fn in tests:
        try:
            print(f"\n--- {name} ---")
            test_fn()
            passed += 1
        except Exception as e:
            print(f"❌ FAILED: {e}")
            failed += 1
    
    print("\n" + "=" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    
    if failed > 0:
        sys.exit(1)
    
    # Write reward
    with open("/logs/verifier/reward.txt", "w") as f:
        f.write("1.0")
    print("\n✅ All tests passed! Reward: 1.0")

if __name__ == "__main__":
    main()
