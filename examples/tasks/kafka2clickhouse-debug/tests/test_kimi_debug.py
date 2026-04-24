#!/usr/bin/env python3
"""
Test Kimi's static analysis ability on Kafka-to-ClickHouse bug.
Uses shared kimi_client (KIMI_API_KEY / KIMI_URL / KIMI_MODEL).
"""

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from kimi_client import call_kimi, KIMI_MODEL


def main():
    print("Testing Kimi: Kafka-to-ClickHouse Bug Analysis")

    task_dir = Path(__file__).parent.parent
    output_dir = task_dir / "results"
    output_dir.mkdir(exist_ok=True)

    instruction = (task_dir / "instruction.md").read_text()
    code = (task_dir / "app" / "code" / "ReadBufferFromKafkaConsumer.cpp").read_text()
    header = (task_dir / "app" / "code" / "ReadBufferFromKafkaConsumer.h").read_text()

    prompt = f"""You are a senior C++ engineer debugging a production issue.

{instruction}

===== ReadBufferFromKafkaConsumer.h =====
```cpp
{header}
```

===== ReadBufferFromKafkaConsumer.cpp =====
```cpp
{code}
```

Please answer:

**Bug Location:**
- File: [filename]
- Line: [line number]

**Fix:**
```cpp
[code to add]
```

**Explanation:**
[2-3 sentences explaining why this fixes the rebalance issue]"""

    print(f"Calling {KIMI_MODEL}...", end=" ", flush=True)
    start = time.time()
    response = call_kimi([{"role": "user", "content": prompt}])
    elapsed = time.time() - start
    print(f"✓ ({elapsed:.1f}s)")

    result = {
        "task": "kafka2clickhouse-debug",
        "model": KIMI_MODEL,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_seconds": round(elapsed, 2),
        "response": response,
        "expected_fix": {
            "file": "ReadBufferFromKafkaConsumer.cpp",
            "line": 395,
            "code": "waited_for_assignment = 0;",
        },
    }
    (output_dir / "kimi_debug_test.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    (output_dir / "kimi_debug_response.txt").write_text(response)

    print("\n=== Response ===")
    print(response)
    print("\n=== Checks ===")
    print("✓ file" if "ReadBufferFromKafkaConsumer.cpp" in response else "✗ file")
    lines = [int(m) for m in re.findall(r'\b(\d+)\b', response)]
    close = [l for l in lines if abs(l - 395) <= 10]
    print(f"✓ line ~{close[0]}" if close else "✗ line not found")
    print("✓ fix" if "waited_for_assignment" in response else "✗ fix")
    print(f"\nSaved to {output_dir}/")


if __name__ == "__main__":
    main()
