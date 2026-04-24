# Kafka to ClickHouse Debug Task

## Background

You are debugging a production issue in a Kafka-to-ClickHouse real-time ingestion pipeline. The system uses ClickHouse's Kafka engine to consume messages and write them to ClickHouse tables.

**System Architecture:**
```
Kafka Topic → ClickHouse Kafka Engine → Target Table
```

**Key Files:**
- `ReadBufferFromKafkaConsumer.cpp` - Core consumer logic
- `ReadBufferFromKafkaConsumer.h` - Header file

## Problem Description

**Symptom:**
- Daily ingestion is stable with controlled small file counts
- When Kafka topic **rebalance** happens, small file count suddenly increases
- The problem **does NOT auto-recover** - requires ClickHouse consumer restart
- After restart, everything works normally until next rebalance

**Context:**
- The system implements **batch accumulation** (攒批) to reduce write fragmentation
- `poll()` function controls how messages are fetched from Kafka
- `waited_for_assignment` variable tracks time waiting for partition assignment

## Key Variables

```cpp
const auto MAX_TIME_TO_WAIT_FOR_ASSIGNMENT_MS = 15000;  // 15 seconds
const std::size_t POLL_TIMEOUT_WO_ASSIGNMENT_MS = 50;   // short timeout

size_t waited_for_assignment = 0;  // tracks waiting time for assignment
const size_t poll_timeout = 500;   // normal poll timeout (ms)
```

## Key Logic

The `poll()` function uses `waited_for_assignment` to adjust poll timeout:

```cpp
// Line 342-344
auto actual_poll_timeout_ms = (waited_for_assignment >= MAX_TIME_TO_WAIT_FOR_ASSIGNMENT_MS)
    ? std::min(POLL_TIMEOUT_WO_ASSIGNMENT_MS, poll_timeout)  // short timeout (50ms)
    : poll_timeout;  // normal timeout (500ms)
```

**Logic:**
- If waiting < 15 seconds: use **long timeout** (500ms) for better batching
- If waiting >= 15 seconds: use **short timeout** (50ms) to avoid blocking

## Rebalance Logic

When rebalance happens (revocation callback, line 58-86):
```cpp
consumer->set_revocation_callback([this](...) {
    cleanUnprocessed();
    stalled_status = REBALANCE_HAPPENED;
    assignment.clear();
    waited_for_assignment = 0;  // RESET HERE
});
```

## Your Task

**Find the ONE-LINE bug fix** that resolves the rebalance issue.

Requirements:
1. Analyze the `poll()` function logic (lines 317-414)
2. Understand the relationship between `waited_for_assignment` and poll timeout
3. Identify what should happen after successfully polling messages
4. Add exactly **one line of code** to fix the issue

## Hints

1. Read lines 367-400 carefully - what happens after messages are polled?
2. Consider the lifecycle of `waited_for_assignment`:
   - Reset to 0 on revocation (line 75)
   - Incremented when no assignment (line 373)
   - But what about when messages are successfully polled?
3. Think about the difference between:
   - "Waiting for assignment" (initial connection)
   - "After rebalance with successful poll" (normal operation)

## Expected Answer Format

Provide:
1. The exact line number where code should be added
2. The exact line of code to add
3. A 2-3 sentence explanation of why this fixes the issue

## Analysis Steps

Follow these steps:
1. Read the entire `poll()` function
2. Trace `waited_for_assignment` variable usage
3. Identify the missing reset logic
4. Explain the bug impact on batching behavior
5. Provide the fix

Good luck! 🔍
