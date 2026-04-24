#!/usr/bin/env python3
"""
ClickHouse vs Doris 前缀索引 Benchmark 完整脚本

场景: 电商卖家 × 商品 × 日期聚合表
规模: 10K sellers × 100 items/seller × ~3 active/day × 365 days ≈ 13M rows

用法:
    python gen_test_data.py --target both --create-tables --run-queries
    python gen_test_data.py --sellers 500 --days 30 --create-tables --run-queries  # 快速验证
"""

import argparse
import random
import datetime
import time
import sys
from typing import List, Tuple

# ============================================================
# 配置
# ============================================================
CK_HOST, CK_PORT, CK_DB = 'localhost', 9000, 'default'
DORIS_HOST, DORIS_PORT = 'localhost', 9030
DORIS_USER, DORIS_PASS, DORIS_DB = 'root', '', 'ads'

TABLE = 'ads_seller_item_stat'
BATCH_SIZE = 100_000
SEED = 42

# ============================================================
# DDL
# ============================================================
CK_DDL = """
CREATE TABLE IF NOT EXISTS {tbl} (
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

    -- Q2: bloom_filter FPR 2.5%, ~97% granules 跳过
    INDEX idx_item_id   item_id     TYPE bloom_filter(0.025) GRANULARITY 1,
    -- Q3: set(512) 精确匹配, ~70% granules 跳过
    INDEX idx_category  category_id TYPE set(512)           GRANULARITY 1
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(p_date)
ORDER BY (seller_id, item_id)
SETTINGS index_granularity = 8192
"""

DORIS_DDL = """
CREATE TABLE IF NOT EXISTS {tbl} (
    p_date        DATE NOT NULL,
    seller_id     VARCHAR(16) NOT NULL COMMENT 'S_00001234',
    item_id       VARCHAR(16) NOT NULL COMMENT 'ITEM_000012345',
    category_id   INT NOT NULL DEFAULT '0',
    sub_cat_name  VARCHAR(32),
    imp_cnt       BIGINT DEFAULT '0',
    clk_cnt       BIGINT DEFAULT '0',
    order_cnt     INT DEFAULT '0',
    order_amt     DOUBLE DEFAULT '0',
    refund_cnt    INT DEFAULT '0',
    refund_amt    DOUBLE DEFAULT '0',

    INDEX idx_item_id (item_id) USING INVERTED PROPERTIES("parser"="none"),
    INDEX idx_category (category_id) USING INVERTED
) ENGINE = OLAP
DUPLICATE KEY(seller_id, item_id)
PARTITION BY RANGE(p_date)(
    FROM ("2025-01-01") TO ("2026-01-01") INTERVAL 1 MONTH
)
DISTRIBUTED BY HASH(seller_id) BUCKETS 4
PROPERTIES(
    "replication_num" = "1",
    "compaction_policy" = "time_series"
)
"""

# ============================================================
# 查询
# ============================================================
QUERIES = [
    {
        'label': 'Q1 卖家7日看板',
        'note_ck': 'ORDER BY 首列 seller_id → sparse index 精准',
        'note_doris': 'DUPLICATE KEY 首列 → short key index 命中',
        'ck': """
            SELECT seller_id,
                   sum(imp_cnt) AS total_imp, 
                   sum(clk_cnt) AS total_clk,
                   sum(order_cnt) AS total_orders, 
                   round(sum(order_amt), 2) AS total_gmv
            FROM {tbl}
            WHERE seller_id = 'S_00001234'
              AND p_date BETWEEN '2025-04-16' AND '2025-04-22'
            GROUP BY seller_id
        """,
        'doris': """
            SELECT seller_id,
                   sum(imp_cnt) AS total_imp, 
                   sum(clk_cnt) AS total_clk,
                   sum(order_cnt) AS total_orders, 
                   round(sum(order_amt), 2) AS total_gmv
            FROM {tbl}
            WHERE seller_id = 'S_00001234'
              AND p_date BETWEEN '2025-04-16' AND '2025-04-22'
            GROUP BY seller_id
        """
    },
    {
        'label': 'Q2 商品跨月趋势',
        'note_ck': 'bloom_filter FPR 2.5%',
        'note_doris': 'Inverted Index FPR 0%',
        'ck': """
            SELECT p_date, seller_id, imp_cnt, order_amt
            FROM {tbl}
            WHERE item_id = 'ITEM_000012345'
              AND p_date BETWEEN '2025-01-01' AND '2025-04-22'
            ORDER BY p_date
        """,
        'doris': """
            SELECT p_date, seller_id, imp_cnt, order_amt
            FROM {tbl}
            WHERE item_id = 'ITEM_000012345'
              AND p_date BETWEEN '2025-01-01' AND '2025-04-22'
            ORDER BY p_date
        """
    },
    {
        'label': 'Q3 品类竞争力',
        'note_ck': 'set(512) 精确匹配',
        'note_doris': 'Inverted Index FPR 0%',
        'ck': """
            SELECT seller_id,
                   count(DISTINCT item_id) AS active_items,
                   round(sum(order_amt), 2) AS gmv
            FROM {tbl}
            WHERE category_id = 123
              AND p_date BETWEEN '2025-04-01' AND '2025-04-22'
            GROUP BY seller_id
            HAVING sum(order_amt) > 1000
            ORDER BY gmv DESC
            LIMIT 100
        """,
        'doris': """
            SELECT seller_id,
                   count(DISTINCT item_id) AS active_items,
                   round(sum(order_amt), 2) AS gmv
            FROM {tbl}
            WHERE category_id = 123
              AND p_date BETWEEN '2025-04-01' AND '2025-04-22'
            GROUP BY seller_id
            HAVING sum(order_amt) > 1000
            ORDER BY gmv DESC
            LIMIT 100
        """
    }
]

# ============================================================
# 数据生成
# ============================================================
def build_seller_meta(num_sellers: int, items_per_seller=100, 
                      cats_per_seller=5, num_cats=500) -> list:
    """预计算 seller 元数据，保证 seller→item→category 关联一致"""
    rng = random.Random(SEED)
    return [
        (
            f"S_{i:08d}",
            [f"ITEM_{i * items_per_seller + j:09d}" for j in range(items_per_seller)],
            rng.sample(range(1, num_cats + 1), cats_per_seller)
        )
        for i in range(num_sellers)
    ]

def gen_day(date: datetime.date, meta: list, rng: random.Random) -> List[Tuple]:
    """生成某天的所有行，每个 seller 随机激活 2~5 个 item"""
    rows = []
    for sid, items, cats in meta:
        for item_id in rng.sample(items, rng.randint(2, 5)):
            imp = rng.randint(100, 10_000)
            clk = max(1, int(imp * rng.uniform(0.02, 0.15)))
            orders = max(0, int(clk * rng.uniform(0.05, 0.30)))
            amt = round(orders * rng.uniform(20.0, 500.0), 2)
            refund = max(0, int(orders * rng.uniform(0.0, 0.05)))
            cat = rng.choice(cats)
            rows.append((
                date, sid, item_id, cat, f"Cat_{cat:03d}",
                imp, clk, orders, amt,
                refund, round(refund * rng.uniform(20.0, 300.0), 2)
            ))
    return rows

# ============================================================
# ClickHouse 连接
# ============================================================
def ck_connect(args):
    try:
        from clickhouse_driver import Client
        return Client(host=args.ck_host, port=args.ck_port, database=args.ck_db)
    except ImportError:
        print("Error: clickhouse-driver not installed. Run: pip install clickhouse-driver")
        sys.exit(1)

def ck_create(c):
    c.execute(f"DROP TABLE IF EXISTS {TABLE}")
    c.execute(CK_DDL.format(tbl=TABLE))
    print(f"[CK] ✓ {TABLE} created")

def ck_flush(c, buf: list):
    c.execute(
        f"INSERT INTO {TABLE} "
        f"(p_date,seller_id,item_id,category_id,sub_cat_name,"
        f"imp_cnt,clk_cnt,order_cnt,order_amt,refund_cnt,refund_amt) VALUES",
        buf
    )

def ck_query(c, sql: str) -> list:
    return c.execute(sql.format(tbl=TABLE))

# ============================================================
# Doris 连接
# ============================================================
def doris_connect(args):
    try:
        import mysql.connector
        return mysql.connector.connect(
            host=args.doris_host, port=args.doris_port,
            user=args.doris_user, password=args.doris_pass,
            database=args.doris_db, autocommit=True
        )
    except ImportError:
        print("Error: mysql-connector-python not installed. Run: pip install mysql-connector-python")
        sys.exit(1)

def doris_create(conn):
    cur = conn.cursor()
    cur.execute(f"DROP TABLE IF EXISTS {TABLE}")
    cur.execute(DORIS_DDL.format(tbl=TABLE))
    cur.close()
    print(f"[Doris] ✓ {TABLE} created")

def doris_flush(conn, buf: list):
    cur = conn.cursor()
    cur.executemany(
        f"INSERT INTO {TABLE} "
        f"(p_date,seller_id,item_id,category_id,sub_cat_name,"
        f"imp_cnt,clk_cnt,order_cnt,order_amt,refund_cnt,refund_amt) "
        f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        buf
    )
    cur.close()

def doris_query(conn, sql: str) -> list:
    cur = conn.cursor()
    cur.execute(sql.format(tbl=TABLE))
    r = cur.fetchall()
    cur.close()
    return r

# ============================================================
# 写入主循环
# ============================================================
def run_insert(args, ck, doris, use_ck: bool, use_doris: bool):
    start = datetime.date.fromisoformat(args.start_date)
    meta = build_seller_meta(args.sellers)
    rng = random.Random(SEED + 1)

    ck_buf, d_buf = [], []
    total, t0 = 0, time.time()
    est = args.sellers * 3 * args.days
    print(f"Generating data: {args.sellers} sellers × {args.days} days, ~{est:,} rows estimated")

    for d in range(args.days):
        rows = gen_day(start + datetime.timedelta(days=d), meta, rng)

        if use_ck:    ck_buf.extend(rows)
        if use_doris: d_buf.extend(rows)
        total += len(rows)

        if len(ck_buf) >= BATCH_SIZE:
            ck_flush(ck, ck_buf);      ck_buf = []
        if len(d_buf) >= BATCH_SIZE:
            doris_flush(doris, d_buf); d_buf = []

        if (d + 1) % 30 == 0 or d == args.days - 1:
            dt = time.time() - t0
            print(f"  {start + datetime.timedelta(days=d)}  "
                  f"{total:>10,} rows  {total/dt:>8,.0f} r/s", flush=True)

    if ck_buf:  ck_flush(ck, ck_buf)
    if d_buf:   doris_flush(doris, d_buf)
    print(f"✓ Done: {total:,} rows in {time.time()-t0:.1f}s")

# ============================================================
# 查询对比
# ============================================================
def run_queries(ck, doris):
    print(f"\n{'─'*80}")
    print(f"{'Query':<24} {'System':<8} {'Rows':>6} {'ms':>10}  Index Path")
    print(f"{'─'*80}")
    
    results = []
    for q in QUERIES:
        for sys_name, client, sql_key, note_key in [
            ('CK', ck, 'ck', 'note_ck'),
            ('Doris', doris, 'doris', 'note_doris'),
        ]:
            if client is None:
                continue
            
            fn = ck_query if sys_name == 'CK' else doris_query
            t0 = time.time()
            try:
                r = fn(client, q[sql_key])
                ms = (time.time() - t0) * 1000
                print(f" {q['label']:<22} {sys_name:<8} {len(r):>6} {ms:>9.1f}ms  {q[note_key]}")
                results.append({
                    'query': q['label'],
                    'system': sys_name,
                    'rows': len(r),
                    'ms': round(ms, 2),
                    'success': True
                })
            except Exception as e:
                print(f" {q['label']:<22} {sys_name:<8} ERROR: {str(e)[:50]}")
                results.append({
                    'query': q['label'],
                    'system': sys_name,
                    'error': str(e),
                    'success': False
                })
    
    print(f"{'─'*80}")
    return results

# ============================================================
# kimi-k2.5 测试
# ============================================================
def test_kimi_sql_generation():
    """测试 Kimi 的 SQL 生成能力"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    try:
        from kimi_client import call_kimi, KIMI_MODEL
    except ImportError:
        print("Warning: kimi_client not available, skipping kimi test")
        return None

    prompt = f"""Given the ClickHouse table:

```sql
{CK_DDL.format(tbl=TABLE)}
```

Generate an optimized Doris table that:
1. Uses DUPLICATE KEY model
2. Maximizes prefix index coverage (36 bytes limit)
3. Uses INVERTED INDEX for item_id and category_id
4. Ensures query performance for:
   - Q1: WHERE seller_id = 'S_00001234'
   - Q2: WHERE item_id = 'ITEM_000012345'
   - Q3: WHERE category_id = 123

Output only the CREATE TABLE statement:"""

    try:
        content = call_kimi([{"role": "user", "content": prompt}], temperature=0.3, max_tokens=2048)

        checks = {
            "DUPLICATE KEY": "DUPLICATE KEY" in content.upper(),
            "seller_id first": content.find("seller_id") < content.find("item_id") if "seller_id" in content and "item_id" in content else False,
            "INVERTED INDEX for item_id": "INVERTED" in content.upper() and "item_id" in content.lower(),
            "INVERTED INDEX for category": "INVERTED" in content.upper() and "category" in content.lower(),
        }

        score = sum(checks.values()) / len(checks) * 100
        print(f"\n[{KIMI_MODEL} SQL Generation Score: {score:.0f}%]")
        for check, passed in checks.items():
            print(f"  {'✓' if passed else '✗'} {check}")

        return {'score': score, 'checks': checks, 'sql': content[:500]}

    except Exception as e:
        print(f"Error testing kimi: {e}")
        return {'error': str(e)}

# ============================================================
# Main
# ============================================================
def main():
    p = argparse.ArgumentParser(description='CK vs Doris 前缀索引 Benchmark')
    p.add_argument('--target', choices=['ck', 'doris', 'both'], default='both')
    p.add_argument('--create-tables', action='store_true')
    p.add_argument('--run-queries', action='store_true')
    p.add_argument('--skip-insert', action='store_true')
    p.add_argument('--test-kimi', action='store_true', help='Test kimi-k2.5 SQL generation')
    p.add_argument('--sellers', type=int, default=10_000)
    p.add_argument('--days', type=int, default=365)
    p.add_argument('--start-date', default='2025-01-01')
    p.add_argument('--ck-host', default=CK_HOST)
    p.add_argument('--ck-port', type=int, default=CK_PORT)
    p.add_argument('--ck-db', default=CK_DB)
    p.add_argument('--doris-host', default=DORIS_HOST)
    p.add_argument('--doris-port', type=int, default=DORIS_PORT)
    p.add_argument('--doris-user', default=DORIS_USER)
    p.add_argument('--doris-pass', default=DORIS_PASS)
    p.add_argument('--doris-db', default=DORIS_DB)
    args = p.parse_args()

    use_ck    = args.target in ('ck', 'both')
    use_doris = args.target in ('doris', 'both')

    ck    = ck_connect(args)    if use_ck    else None
    doris = doris_connect(args) if use_doris else None

    if args.create_tables:
        if ck:    ck_create(ck)
        if doris: doris_create(doris)

    if not args.skip_insert:
        run_insert(args, ck, doris, use_ck, use_doris)

    results = []
    if args.run_queries:
        results = run_queries(ck, doris)
    
    kimi_result = None
    if args.test_kimi:
        kimi_result = test_kimi_sql_generation()
    
    # 输出汇总
    print("\n" + "="*80)
    print("BENCHMARK SUMMARY")
    print("="*80)
    
    if results:
        print("\nQuery Performance:")
        for r in results:
            if r.get('success'):
                print(f"  {r['query']:<20} {r['system']:<6} {r['rows']:>5} rows in {r['ms']:>7.1f}ms")
    
    if kimi_result:
        print(f"\nkimi-k2.5 Score: {kimi_result.get('score', 0):.0f}%")
    
    print("\n" + "="*80)

if __name__ == '__main__':
    main()
