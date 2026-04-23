#!/usr/bin/env python3
"""
生成 ads_seller_item_stat 测试数据
- 时间范围：2025-01-01 ~ 2025-04-22 (约112天)
- 卖家数：10000
- 商品数：每个卖家 10-50 个商品
- 品类数：500
- 总行数：约 100 万行
"""

import random
import string
from datetime import datetime, timedelta
import subprocess
import sys

# 配置
START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2025, 4, 22)
NUM_SELLERS = 1000  # 降低规模以加速测试
MIN_ITEMS_PER_SELLER = 5
MAX_ITEMS_PER_SELLER = 20
NUM_CATEGORIES = 100
NUM_DAYS = (END_DATE - START_DATE).days + 1

def gen_seller_id(i):
    return f"S_{i:08d}"  # S_00000001

def gen_item_id(i):
    return f"ITEM_{i:010d}"  # ITEM_0000000001

def gen_category_name(cat_id):
    names = ["电子产品", "服装", "食品", "家居", "美妆", "运动", "图书", "玩具", "母婴", "汽车"]
    return f"{names[cat_id % len(names)]}_{cat_id:03d}"

def main():
    random.seed(42)
    
    # 预生成卖家和商品
    sellers = [gen_seller_id(i) for i in range(1, NUM_SELLERS + 1)]
    categories = list(range(1, NUM_CATEGORIES + 1))
    
    # 为每个卖家分配商品
    seller_items = {}
    item_counter = 1
    for seller in sellers:
        num_items = random.randint(MIN_ITEMS_PER_SELLER, MAX_ITEMS_PER_SELLER)
        seller_items[seller] = [gen_item_id(item_counter + j) for j in range(num_items)]
        item_counter += num_items
    
    # 生成 INSERT 语句
    insert_sql = """
    INSERT INTO ads.seller_item_stat
    (p_date, seller_id, item_id, category_id, sub_cat_name, imp_cnt, clk_cnt, order_cnt, order_amt, refund_cnt, refund_amt)
    VALUES
    """
    
    values = []
    batch_size = 50000
    total_rows = 0
    
    print(f"Generating data for {NUM_SELLERS} sellers over {NUM_DAYS} days...")
    
    for day_offset in range(NUM_DAYS):
        p_date = (START_DATE + timedelta(days=day_offset)).strftime('%Y-%m-%d')
        
        for seller in sellers:
            for item in seller_items[seller]:
                cat_id = random.choice(categories)
                sub_cat_name = gen_category_name(cat_id)
                
                # 模拟电商指标分布
                imp_cnt = random.randint(100, 10000)
                clk_cnt = max(0, int(imp_cnt * random.uniform(0.01, 0.15)))
                order_cnt = max(0, int(clk_cnt * random.uniform(0.01, 0.3)))
                order_amt = round(order_cnt * random.uniform(50, 500), 2)
                refund_cnt = max(0, int(order_cnt * random.uniform(0, 0.1)))
                refund_amt = round(refund_cnt * random.uniform(30, 300), 2)
                
                values.append(
                    f"('{p_date}', '{seller}', '{item}', {cat_id}, '{sub_cat_name}', "
                    f"{imp_cnt}, {clk_cnt}, {order_cnt}, {order_amt}, {refund_cnt}, {refund_amt})"
                )
                total_rows += 1
                
                # 批量插入
                if len(values) >= batch_size:
                    sql = insert_sql + ",\n".join(values) + ";"
                    print(f"Inserting batch: {total_rows} rows...")
                    try:
                        subprocess.run(
                            ["clickhouse-client", "--multiquery", "--query", sql],
                            check=True
                        )
                    except subprocess.CalledProcessError as e:
                        print(f"Error inserting batch: {e}")
                        sys.exit(1)
                    values = []
    
    # 插入剩余数据
    if values:
        sql = insert_sql + ",\n".join(values) + ";"
        subprocess.run(["clickhouse-client", "--multiquery", "--query", sql], check=True)
    
    print(f"Total rows inserted: {total_rows}")
    return total_rows

if __name__ == "__main__":
    main()
