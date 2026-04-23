#!/usr/bin/env python3
"""
Generate /data/events.bin — 500,000 events, 24-byte little-endian records.

struct Event {
    uint64_t event_ts_ms;
    uint32_t user_id;
    uint16_t category_id;
    uint16_t watch_seconds;
};

Design goals that make the problem hard:
- ~10,000 distinct users (user_id in 0..99999 but sparse)
- Out-of-order events (jitter up to ±5 s)
- Each user has ~50 events spread over a 120-second wall range,
  so only ~25% of events fall inside the final 30-second window.
- Some users have duplicate (user_id, category_id) across window/non-window,
  trapping agents that skip the timestamp check.
"""
import struct
import random
import os

SEED = 20240422
random.seed(SEED)

N_EVENTS   = 500_000
N_USERS    = 10_000
WINDOW_MS  = 30_000   # 30 seconds
BASE_TS_MS = 1_700_000_000_000  # epoch anchor

# Assign each user a "stream end" time (their personal max_ts)
user_max_ts = {uid: BASE_TS_MS + random.randint(0, 3_600_000)
               for uid in range(N_USERS)}

events = []
user_ids = list(range(N_USERS))

for _ in range(N_EVENTS):
    uid  = random.choice(user_ids)
    cat  = random.randint(0, 999)
    ws   = random.randint(1, 600)

    # Events uniformly distributed in [max_ts - 120_000, max_ts]
    # so ~25% land in [max_ts - 30_000, max_ts] (the window)
    offset = random.randint(-120_000, 0)
    base_ts = user_max_ts[uid] + offset

    # Add jitter ±5000 ms (simulates out-of-order delivery)
    jitter = random.randint(-5_000, 5_000)
    ts = max(0, base_ts + jitter)

    events.append((ts, uid, cat, ws))

# Shuffle to destroy any inherent order
random.shuffle(events)

# 24-byte record: uint64(8) + uint32(4) + uint16(2) + uint16(2) + 8 bytes explicit pad = 24
fmt = "<QIHH8x"  # 8+4+2+2+8(pad) = 24 bytes

os.makedirs("/data", exist_ok=True)

with open("/data/events.bin", "wb") as f:
    for ts, uid, cat, ws in events:
        f.write(struct.pack(fmt, ts, uid, cat, ws))

print(f"Written {len(events)} events to /data/events.bin ({len(events)*24} bytes)")
