#!/usr/bin/env python3
"""Test kimi-k2.5's ability to fix distributed-chaos-system"""

import os
import tempfile
import subprocess
import requests
import json
import shutil

API_KEY = os.environ.get("BAILIAN_API_KEY", "")
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "kimi-k2.5"

# Read the buggy code
buggy_files = {
    "mutation.py": """import random

class MutationEngine:

    def mutate_factor(self):
        return 1.0 if random.random() < 0.95 else 1.07""",

    "commit_graph.py": """import random

class CommitGraph:

    def commit(self):
        return random.random() < 0.97""",

    "replay.py": """import random

def replay(events):

    if random.random() < 0.1:
        events.append({
            "user_id": -1,
            "amount": 999,
            "event_id": 999999,
            "timestamp": 0,
            "source": "synthetic"
        })

    return events"""
}

instruction = """This is a distributed billing system that produces different results on every run.

## Symptoms
- ledger_size varies between runs (48400-48600 instead of 50000)
- replay produces different results
- phantom transactions occasionally appear

## Constraints (MUST preserve)
- WAL functionality must exist
- commit() must be called (but can be deterministic)
- normalize_event() must handle both user_id and uid fields
- System must be deterministic under replay

Analyze the code and fix the non-determinism."""

prompt = f"""{instruction}

Files to fix:

=== mutation.py ===
```python
{buggy_files['mutation.py']}
```

=== commit_graph.py ===
```python
{buggy_files['commit_graph.py']}
```

=== replay.py ===
```python
{buggy_files['replay.py']}
```

Output the COMPLETE FIXED code for each file.
Format as:
```python
# mutation.py fixed code
```"""

print("Testing kimi-k2.5 on distributed-chaos-system...")
print()

try:
    response = requests.post(
        f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 4096
        },
        timeout=120
    )

    content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    print(f"Response length: {len(content)} chars")
    print()

    # Parse the response to extract fixed code
    fixed_files = {}
    current_file = None
    current_code = []
    in_code_block = False

    for line in content.split('\n'):
        if '```python' in line:
            in_code_block = True
            current_code = []
            continue
        elif '```' in line and in_code_block:
            in_code_block = False
            if current_file and current_code:
                fixed_files[current_file] = '\n'.join(current_code)
            continue
        
        if in_code_block:
            # Detect which file this is for
            if 'class MutationEngine' in line:
                current_file = 'mutation.py'
            elif 'class CommitGraph' in line:
                current_file = 'commit_graph.py'
            elif 'def replay' in line:
                current_file = 'replay.py'
            current_code.append(line)

    print(f"Parsed {len(fixed_files)} fixed files: {list(fixed_files.keys())}")
    print()

    # Check for key fixes
    print("=== Checking for non-determinism fixes ===")

    for fn in ['mutation.py', 'commit_graph.py', 'replay.py']:
        if fn in fixed_files:
            code = fixed_files[fn]
            has_random = 'random.random()' in code
            is_deterministic = False
            
            if fn == 'mutation.py':
                is_deterministic = 'return 1.0' in code and 'random' not in code
            elif fn == 'commit_graph.py':
                is_deterministic = 'return True' in code and 'random' not in code
            elif fn == 'replay.py':
                is_deterministic = 'return events' in code and 'append' not in code

            status = '✅ FIXED' if is_deterministic else '❌ STILL BUGGY'
            print(f"{fn}: {status}")
            print(f"  Code: {code[:150]}...")
        else:
            print(f"{fn}: ❌ Not provided")

    # Test by running
    print("\n=== Testing fixed code ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Write a simple test script
        test_main = '''
import json

class WAL:
    def __init__(self):
        self.log = []
    def append(self, e):
        self.log.append(e)

class Cache:
    def __init__(self):
        self.data = {}
    def get(self, uid):
        return self.data.get(uid, 0)
    def set(self, uid, val):
        self.data[uid] = val

class Ledger:
    def __init__(self):
        self.records = []
    def write(self, uid, amt):
        self.records.append((uid, amt))

# Load fixed modules
'''
        # Add imports for fixed files
        for fn in ['mutation', 'commit_graph', 'replay']:
            if fn in fixed_files or fn.replace('_', '_') in fixed_files:
                test_main += f'exec(open("{fn}.py").read())\n'

        # Write fixed files
        for fn, code in fixed_files.items():
            with open(os.path.join(tmpdir, fn), 'w') as f:
                f.write(code)

        # Write test main
        test_main += '''
def run_test():
    wal = WAL()
    cache = Cache()
    ledger = Ledger()
    
    # Simulate Billing.process
    m = MutationEngine()
    c = CommitGraph()
    seen = set()
    
    for i in range(50000):
        if not c.commit():
            continue
        
        event = {"user_id": i % 2000, "amount": 1, "event_id": i}
        factor = m.mutate_factor()
        event["amount"] *= factor
        
        tx_id = (event["user_id"], event["event_id"])
        if tx_id in seen:
            continue
        seen.add(tx_id)
        
        bal = cache.get(event["user_id"])
        bal += event["amount"]
        cache.set(event["user_id"], bal)
        ledger.write(event["user_id"], event["amount"])
        wal.append(event)
    
    return {"ledger_size": len(ledger.records), "replay_size": len(wal.log)}

# Run twice
r1 = run_test()
r2 = run_test()
print(f"Run 1: {r1}")
print(f"Run 2: {r2}")
print(f"Deterministic: {r1 == r2}")
'''
        with open(os.path.join(tmpdir, 'test_main.py'), 'w') as f:
            f.write(test_main)

        # Run test
        result = subprocess.run(
            ['python3', 'test_main.py'],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            timeout=30
        )

        print(result.stdout)
        if result.stderr:
            print(f"STDERR: {result.stderr}")

        if 'Deterministic: True' in result.stdout:
            print("\n✅ KIMI-K2.5 SUCCESSFULLY FIXED THE NON-DETERMINISM!")
        else:
            print("\n❌ FIX INCOMPLETE - Still non-deterministic")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
