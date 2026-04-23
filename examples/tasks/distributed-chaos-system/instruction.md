# Distributed Chaos System Debug

## Problem

A billing system produces **different results on every run** with the same input data. You need to make it **deterministic**.

## Symptoms Observed

```
Run 1: {"ledger_size": 48534, "users": 2000}
Run 2: {"ledger_size": 48492, "users": 2000}
Run 3: {"ledger_size": 48482, "users": 2000}
```

The ledger size varies by ~50 records between runs. Additionally:
- Occasional "phantom" transactions appear (user_id: -1)
- Replay produces different results than the original run
- Missing records in some runs

## Code Locations

| File | Purpose |
|------|---------|
| `app/main.py` | Entry point - processes events |
| `app/billing.py` | Core billing logic |
| `app/mutation.py` | Amount mutation engine |
| `app/commit_graph.py` | Transaction commit logic |
| `app/replay.py` | Event replay handler |
| `app/schema.py` | Event normalization |
| `app/wal.py` | Write-ahead log |
| `app/cache.py` | User balance cache |
| `app/ledger.py` | Final ledger storage |

## Constraints

You MUST preserve:
1. **WAL functionality** - don't remove the WAL class
2. **Retry logic** - `commit_graph.commit()` should exist and be called
3. **Schema evolution support** - `normalize_event()` must handle both `user_id` and `uid` fields
4. **Deterministic replay** - given the same WAL, replay must produce identical ledger

You MAY:
- Add seeding to make random operations deterministic
- Modify mutation/commit/replay behavior (while keeping the APIs)
- Add additional state tracking
- Restructure the processing flow

## Test Criteria

```python
# test_state.py verifies:
r1 = run_system()  # First run
r2 = run_system()  # Second run

assert r1 == r2           # Determinism
assert r1["ledger_size"] > 35000  # Most events processed
assert no_phantom_transactions(r1)  # No user_id=-1
```

## Hint

Look for sources of non-determinism in:
- Random number usage without fixed seeds
- Operations that may fail probabilistically
- Functions that modify inputs during replay

The goal is: **same input → same output, every time**.
