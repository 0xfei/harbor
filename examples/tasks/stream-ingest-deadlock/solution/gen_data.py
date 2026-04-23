#!/usr/bin/env python3
"""Generate 100k events for stream-ingest-deadlock test."""
import json
import sys

def main():
    n_events = 100000
    n_shards = 8

    output = sys.argv[1] if len(sys.argv) > 1 else "data/events.jsonl"

    with open(output, "w") as f:
        for i in range(n_events):
            evt = {
                "id": i,
                "shard": i % n_shards,
                "seq": i // n_shards
            }
            f.write(json.dumps(evt) + "\n")

    print(f"Generated {n_events} events to {output}")

if __name__ == "__main__":
    main()
