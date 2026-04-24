# Kafka-to-ClickHouse Debug Task

A static analysis task to test Kimi-k2.5's ability to identify a subtle production bug in a Kafka-to-ClickHouse ingestion pipeline.

## Task Overview

**Type:** Static code analysis, debugging
**Difficulty:** Medium
**Time Limit:** 30 minutes

**Goal:** Identify the ONE-LINE fix for a production bug that causes small file explosion after Kafka rebalance.

## Problem Description

In production:
- Normal operation: stable ingestion, controlled file count
- After Kafka rebalance: small files increase dramatically
- Does NOT auto-recover - requires ClickHouse restart

## Key Concept

The system uses **batch accumulation** (攒批) to control write frequency:

```
Kafka → Poll (攒批) → Batch → Write to ClickHouse
```

**Poll timeout controls batching:**
- Short timeout (50ms): frequent polls, smaller batches
- Long timeout (500ms): fewer polls, larger batches

## The Bug

After rebalance, `waited_for_assignment` is reset to 0, causing the system to use long timeout (500ms) instead of short timeout (50ms).

**Without fix:**
- After rebalance: use 500ms timeout → poor batching → small files

**With fix:**
- After rebalance: return to 50ms timeout → good batching → normal operation

## Files

```
kafka2clickhouse-debug/
├── ReadBufferFromKafkaConsumer.cpp   # Core logic (analyze this!)
├── ReadBufferFromKafkaConsumer.h      # Header
├── instruction.md                     # Task instructions
├── task.toml                          # Task configuration
├── solution/
│   └── solve.sh                       # Answer: Line 395, waited_for_assignment = 0
└── docs/
    └── BUG_ANALYSIS.md                # Detailed analysis
```

## Key Code Section

**Line 342-344:** Poll timeout decision
```cpp
auto actual_poll_timeout_ms = (waited_for_assignment >= MAX_TIME_TO_WAIT_FOR_ASSIGNMENT_MS)
    ? std::min(POLL_TIMEOUT_WO_ASSIGNMENT_MS, poll_timeout)  // 50ms (short)
    : poll_timeout;  // 500ms (long)
```

**Line 75:** Reset on revocation
```cpp
waited_for_assignment = 0;
```

**Line 395:** Where to add the fix
```cpp
messages = std::move(new_messages);
```

## Solution

**File:** `ReadBufferFromKafkaConsumer.cpp`
**Line:** Before line 395
**Code:** `waited_for_assignment = 0;`

**Explanation:** After successfully polling messages, reset `waited_for_assignment` so the next poll uses appropriate timeout for batch accumulation.

## Testing Kimi-k2.5

This task tests:
1. Static code comprehension
2. Variable lifecycle tracking
3. Understanding of batch accumulation logic
4. Production debugging intuition

**Success Criteria:**
- Identifies the correct line (395)
- Identifies the correct fix (`waited_for_assignment = 0`)
- Explains the batching impact

## References

- ClickHouse Kafka Engine: https://clickhouse.com/docs/en/engines/table-engines/integrations/kafka/
- librdkafka rebalancing: https://github.com/edenhill/librdkafka/wiki/Balancing-topic-partitions-across-consumers
- Original issue: Production incident at Kuaishou (internal)
