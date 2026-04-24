# ClickHouse MergeTree Partition Crash Bug

## Background

You are debugging a **production crash** in ClickHouse's MergeTree engine. This is a critical bug introduced when adapting a community feature.

**Context:**
- ClickHouse internally adapted the community PR [#48990](https://github.com/ClickHouse/ClickHouse/pull/48990/changes)
- New feature: `system.parts` now records which partitions were scanned during queries
- Internal adaptation: Convert `partition_id` to human-readable `partition` identifier
- **Bug**: After deployment, certain queries cause ClickHouse process to crash

## Problem Description

**Symptom:**
- ClickHouse process crashes with segmentation fault
- Crash occurs in `MergeTreePartition::serializeText` function
- Specific queries trigger the crash consistently

**Stack Trace (Key Frame):**
```
#0  DB::ColumnVector<unsigned short>::insert(DB::Field const&)
    at ColumnVector.h:280
#1  DB::MergeTreePartition::serializeText(...)
    at MergeTreePartition.cpp:190
#2  DB::MergeTreeDataSelectExecutor::readFromParts(...)
    at MergeTreeDataSelectExecutor.cpp:1320
```

**Crash Location:**
- File: `MergeTreePartition.cpp`
- Line: 190 (`column->insert(value[0]);`)

## Code to Analyze

### `MergeTreePartition.cpp` (Lines 176-210)

```cpp
void MergeTreePartition::serializeText(const MergeTreeData & storage, WriteBuffer & out, const FormatSettings & format_settings) const
{
    auto metadata_snapshot = storage.getInMemoryMetadataPtr();
    const auto & partition_key_sample = metadata_snapshot->getPartitionKey().sample_block;
    size_t key_size = partition_key_sample.columns();

    if (key_size == 0)  // ← Line 182: ONLY checks key_size
    {
        writeCString("tuple()", out);
    }
    else if (key_size == 1)
    {
        const DataTypePtr & type = partition_key_sample.getByPosition(0).type;
        auto column = type->createColumn();
        column->insert(value[0]);  // ← Line 190: CRASH HERE when value is empty
        type->getDefaultSerialization()->serializeText(*column, 0, out, format_settings);
    }
    else
    {
        DataTypes types;
        Columns columns;
        for (size_t i = 0; i < key_size; ++i)
        {
            const auto & type = partition_key_sample.getByPosition(i).type;
            types.push_back(type);
            auto column = type->createColumn();
            column->insert(value[i]);  // ← Line 202: Also crashes if value empty
            columns.push_back(std::move(column));
        }

        auto tuple_serialization = DataTypeTuple(types).getDefaultSerialization();
        auto tuple_column = ColumnTuple::create(columns);
        tuple_serialization->serializeText(*tuple_column, 0, out, format_settings);
    }
}
```

### Member Variable

```cpp
// In MergeTreePartition.h
class MergeTreePartition
{
    // ...
    std::vector<Field> value;  // Can be empty in certain edge cases
    // ...
};
```

## Test Case (Simplified)

**Table Schema:**
```sql
CREATE TABLE test_table
(
    `id` Int64,
    `name` Nullable(String),
    `event_date` Date
)
ENGINE = ReplicatedMergeTree()
PARTITION BY toDate(event_date)
PRIMARY KEY (event_date, id)
ORDER BY (event_date, id)
PROJECTION p1
(
    SELECT event_date, sum(id)
    GROUP BY event_date
)
SETTINGS index_granularity = 8192
```

**Crash Query:**
```sql
SELECT id, SUM(id) AS total
FROM test_table
WHERE toDate(event_date) = '2025-11-12'
GROUP BY id
ORDER BY total DESC
LIMIT 100
```

## Your Task

**Goal:** Identify the ONE-LINE fix that prevents this crash.

**Requirements:**
1. Analyze the `serializeText` function logic
2. Understand the relationship between `key_size` and `value`
3. Identify the edge case that causes the crash
4. Propose a minimal fix (one line of code)

**Hint:**
- The condition at Line 182 only checks `key_size`
- What other condition should be checked?
- Think about the `value` vector's state

## Answer Format

Provide:
1. The exact line to modify (Line 182)
2. The exact condition to add
3. A 2-3 sentence explanation of why this fixes the crash

Good luck! 🔍
