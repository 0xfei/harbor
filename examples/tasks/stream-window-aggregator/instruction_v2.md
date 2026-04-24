# Stream Window Aggregator

## Background

You are working on a **real-time video recommendation pipeline**. The pipeline
ingests a stream of user click events and must continuously maintain, for each
user, the **top-3 most-watched video categories** within a **30-second sliding
window based on event timestamps** (not wall-clock time).

Downstream ranking models poll the aggregation results every few seconds; stale
or incorrect interest profiles degrade recommendation quality directly.

## Your Task

Implement a C++ program `/app/aggregator` that:

1. Reads a **binary event log** from `/data/events.bin` (format described below).
2. Processes events in **4 parallel worker threads** (exactly 4, not more, not fewer).
3. Produces an output file `/data/output.tsv` with the aggregated results.

### Input Format: `/data/events.bin`

The file is a sequence of fixed-size **24-byte records**, **little-endian**:

```c
struct Event {
    uint64_t event_ts_ms;   // event timestamp in milliseconds (event time)
    uint32_t user_id;       // user identifier
    uint16_t category_id;   // video category (0–999)
    uint16_t watch_seconds; // how long the user watched (1–600)
    uint8_t  _pad[8];       // padding to make sizeof(Event) == 24
};
static_assert(sizeof(Event) == 24, "Event must be exactly 24 bytes");
```

The file contains **500,000 events**. Events are **NOT** sorted by timestamp;
they may arrive out-of-order by up to ±5 seconds.

### Output Format: `/data/output.tsv`

For each `user_id` that appears in the input, write exactly one line:

```
<user_id>\t<cat1>:<score1>,<cat2>:<score2>,<cat3>:<score3>
```

Rules:
- The sliding window is **30,000 ms wide** (30 seconds), anchored at the
  **maximum event timestamp seen for that user** (i.e., the window covers
  `[max_ts - 30000, max_ts]` inclusive).
- The score for a category is the **sum of `watch_seconds`** for all events
  within the window for that user+category pair.
- Report the **top-3 categories by score** (ties broken by **lower category_id
  first**).
- If a user has fewer than 3 distinct categories in their window, output only
  the categories that exist (no padding).
- Lines must be sorted in **ascending numeric order of `user_id`** (not
  lexicographic order — `user_id` is a uint32, sort numerically).
- Scores must be integers (no decimal point).

### Mandatory Constraints — Read Carefully

> **CONSTRAINT A — Forbidden synchronization primitives:**
> You MUST NOT use `std::mutex`, `std::lock_guard`, `std::unique_lock`,
> `pthread_mutex_t`, `pthread_rwlock_t`, `sem_t`, or any other blocking lock.
> All shared state must be protected exclusively with **C++ atomic operations**
> (`std::atomic`, `std::atomic_ref`, or `__atomic_*` builtins).
> Violation is detected automatically by the verifier (symbol scan of the binary).

> **CONSTRAINT B — Forbidden data structures:**
> You MUST NOT use `std::map`, `std::unordered_map`, `std::set`,
> `std::unordered_set`, or any other node-based heap-allocated associative
> container for per-user state storage. Use only array-based or ring-buffer
> structures.
> Violation is detected automatically by the verifier (symbol scan of the binary).

> **CONSTRAINT C — Memory limit:**
> The total process RSS must stay below **200 MB** at all times. The verifier
> measures peak RSS. Exceeding this limit results in zero score.

> **CONSTRAINT D — Correctness requirement:**
> The aggregation window uses **event timestamps** (`event_ts_ms`), NOT the
> order in which events are read from disk. An event with `event_ts_ms = T`
> contributes to a user's window only if `T >= max_ts_for_user - 30000`.
> Processing events in file order without tracking event time is a common
> mistake that produces wrong answers.

> **CONSTRAINT E — Thread count:**
> The program must spawn exactly 4 worker threads (you may detect this is
> enforced via `/proc/self/status` Threads field check in the verifier).

> **CONSTRAINT F — No external libraries:**
> You may only use the C++ standard library (C++17 or later) and POSIX APIs.
> Do NOT use Boost, TBB, folly, abseil, or any third-party library.

### Compilation

Your program must compile with:

```bash
g++ -O2 -std=c++17 -pthread -o /app/aggregator /app/aggregator.cpp
```

No other source files. The entire implementation must be in a single file
`/app/aggregator.cpp`.

### Verification Steps

The verifier will:
1. Check that `/app/aggregator` exists and was compiled from `/app/aggregator.cpp`.
2. Run `nm /app/aggregator` and confirm no forbidden symbols are linked.
3. Execute `/app/aggregator` and measure peak RSS.
4. Compare `/data/output.tsv` against the reference answer line-by-line.
5. Check that exactly 4 worker threads were spawned (via thread count sampling).
6. Score is computed as a weighted combination of the above checks.

### Tips

- Think carefully about the window semantics: you need to **finalize** a user's
  window only after all events for that user have been processed. A two-pass
  approach (first pass to find `max_ts` per user, second pass to aggregate) is
  valid **if** it runs within time and memory limits.
- Lock-free designs often require **careful memory ordering**. Using
  `memory_order_relaxed` everywhere is likely incorrect.
- The 200 MB RSS limit is tight. 500,000 users × 1000 categories × 4 bytes =
  2 GB — do NOT allocate a full user×category matrix.

### Example

Given 3 events for user 42:
```
event_ts_ms=1000100, user_id=42, category_id=5, watch_seconds=20
event_ts_ms=1000000, user_id=42, category_id=3, watch_seconds=15
event_ts_ms=970500,  user_id=42, category_id=5, watch_seconds=10
```

max_ts = 1000100, window = [970100, 1000100].
- Event at 970500: inside window → cat5 += 10
- Event at 1000000: inside window → cat3 += 15
- Event at 1000100: inside window → cat5 += 20

Top categories: cat5=30, cat3=15.
Output line: `42\t5:30,3:15`
