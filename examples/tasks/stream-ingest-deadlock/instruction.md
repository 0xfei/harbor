Fix the ingestion system.

Requirements:

1. Process 100000 events
2. No duplicate commits
3. Preserve order per shard
4. Runtime < 15 sec
5. Peak RSS < 500 MB

Constraints:

- Do NOT use asyncio
- Do NOT use multiprocessing
- Stdlib only
- Keep public APIs unchanged