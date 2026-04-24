#!/usr/bin/env python3
"""
Test Kimi-k2.5's ability to debug ClickHouse MergeTree partition crash.
"""

import json
import os
import sys
import time
from pathlib import Path
import requests

# Configuration
API_KEY = os.environ.get("BAILIAN_API_KEY", "")
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "kimi-k2.5"


def call_kimi_api(prompt: str, max_tokens: int = 6000) -> str:
    """Call Bailian API for kimi-k2.5."""
    if not API_KEY:
        raise ValueError("BAILIAN_API_KEY not set")
    
    url = f"{BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": max_tokens
    }
    
    response = requests.post(url, headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def main():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  Testing Kimi-k2.5: ClickHouse MergeTree Crash Debug         ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print("")
    
    # Paths
    task_dir = Path(__file__).parent.parent
    code_file = task_dir / "MergeTreePartition.cpp"
    instruction_file = task_dir / "instruction.md"
    output_dir = task_dir / "results"
    output_dir.mkdir(exist_ok=True)
    
    # Load files
    print("Loading task files...")
    
    with open(instruction_file) as f:
        instruction = f.read()
    
    with open(code_file) as f:
        code = f.read()
    
    print(f"  instruction.md: {len(instruction)} bytes")
    print(f"  MergeTreePartition.cpp: {len(code)} bytes")
    print("")
    
    # Build prompt
    prompt = f"""You are a senior C++ engineer debugging a critical production crash in ClickHouse.

{instruction}

Here is the source file to analyze:

===== MergeTreePartition.cpp =====
```cpp
{code}
```

Please analyze the code and provide your answer in the following format:

**Bug Location:**
- File: [filename]
- Line: [line number]

**Fix:**
- Change: [original code] → [new code]

**Explanation:**
[2-3 sentences explaining why this fixes the crash]

Provide your complete analysis."""

    # Call API
    print("Calling Kimi-k2.5 API...", end=" ", flush=True)
    start_time = time.time()
    
    try:
        response = call_kimi_api(prompt)
        elapsed = time.time() - start_time
        print(f"✓ ({elapsed:.2f}s)")
    except Exception as e:
        print(f"✗ Failed: {e}")
        sys.exit(1)
    
    print(f"\nResponse length: {len(response)} bytes")
    print("")
    
    # Save results
    output = {
        "task": "clickhouse-mergetree-debug",
        "model": MODEL,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_seconds": elapsed,
        "instruction_length": len(instruction),
        "code_length": len(code),
        "response_length": len(response),
        "response": response,
        "expected_fix": {
            "file": "MergeTreePartition.cpp",
            "line": 182,
            "original": "if (key_size == 0)",
            "fixed": "if (key_size == 0 || value.empty())",
            "location_description": "Add value.empty() check to prevent out-of-bounds access"
        }
    }
    
    # Save JSON
    json_path = output_dir / "kimi_debug_test.json"
    with open(json_path, "w") as f:
        json.dump(output, f, indent=2)
    
    # Save raw response
    response_path = output_dir / "kimi_debug_response.txt"
    with open(response_path, "w") as f:
        f.write(f"Kimi-k2.5 Bug Analysis Response\n")
        f.write(f"{'='*60}\n\n")
        f.write(response)
    
    print(f"Results saved:")
    print(f"  JSON: {json_path}")
    print(f"  Text: {response_path}")
    print("")
    
    # Print response
    print("="*60)
    print("Kimi-k2.5 Response:")
    print("="*60)
    print(response)
    print("="*60)
    print("")
    
    # Quick analysis
    print("Quick Analysis:")
    print("-"*60)
    
    # Check if it found the right file
    if "MergeTreePartition.cpp" in response:
        print("✓ Correct file mentioned")
    else:
        print("✗ File not mentioned")
    
    # Check if it found the right line (around 182)
    import re
    line_matches = re.findall(r'line[:\s]+(\d+)', response.lower())
    if line_matches:
        lines = [int(m) for m in line_matches]
        closest = min(lines, key=lambda x: abs(x - 182))
        if abs(closest - 182) <= 5:
            print(f"✓ Line number close to correct (found {closest}, expected ~182)")
        else:
            print(f"✗ Wrong line number (found {closest}, expected ~182)")
    
    # Check if it found the right fix
    if "value.empty()" in response or "value.empty" in response:
        print("✓ Correct fix mentioned")
    else:
        print("✗ Fix not found correctly")
    
    print("-"*60)
    print("")
    print("Full results saved to results/")


if __name__ == "__main__":
    main()
