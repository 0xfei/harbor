#!/usr/bin/env python3
"""
Oracle solver — produces the reference /data/expected.tsv

This is a pure-Python reference implementation with no constraints.
It is run by solve.sh to generate the ground truth.
"""
import struct
import collections
import os

WINDOW_MS = 30_000

fmt = "<QIHH8x"  # 24 bytes per record
record_size = struct.calcsize(fmt)
assert record_size == 24, f"record size mismatch: {record_size}"

# Pass 1: find max_ts per user
user_max_ts = {}
events_raw = []

with open("/data/events.bin", "rb") as f:
    while True:
        raw = f.read(record_size)
        if not raw:
            break
        ts, uid, cat, ws = struct.unpack(fmt, raw)
        events_raw.append((ts, uid, cat, ws))
        if uid not in user_max_ts or ts > user_max_ts[uid]:
            user_max_ts[uid] = ts

# Pass 2: aggregate within window
# user_id -> category_id -> total watch_seconds
user_cat_score = collections.defaultdict(lambda: collections.defaultdict(int))

for ts, uid, cat, ws in events_raw:
    window_start = user_max_ts[uid] - WINDOW_MS
    if ts >= window_start:
        user_cat_score[uid][cat] += ws

# Build output
lines = []
for uid in sorted(user_cat_score.keys()):
    cat_scores = user_cat_score[uid]
    # Sort: descending score, then ascending category_id for ties
    ranked = sorted(cat_scores.items(), key=lambda x: (-x[1], x[0]))[:3]
    parts = ",".join(f"{cat}:{score}" for cat, score in ranked)
    lines.append(f"{uid}\t{parts}")

os.makedirs("/data", exist_ok=True)
with open("/data/expected.tsv", "w") as f:
    f.write("\n".join(lines) + "\n")

print(f"Oracle: wrote {len(lines)} user records to /data/expected.tsv")
