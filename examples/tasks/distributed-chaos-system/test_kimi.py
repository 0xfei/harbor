#!/usr/bin/env python3
"""
Test Kimi's ability to fix distributed-chaos-system non-determinism.
Uses shared kimi_client (KIMI_API_KEY / KIMI_URL / KIMI_MODEL).
"""

import os
import subprocess
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from kimi_client import call_kimi, KIMI_MODEL

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


print(f"Testing Kimi: distributed-chaos-system ({KIMI_MODEL})")
start = time.time()
content = call_kimi([{"role": "user", "content": prompt}], temperature=0.3)
elapsed = time.time() - start
print(f"Response: {elapsed:.1f}s, {len(content)} chars\n")

# Parse fixed files
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
        if 'class MutationEngine' in line:
            current_file = 'mutation.py'
        elif 'class CommitGraph' in line:
            current_file = 'commit_graph.py'
        elif 'def replay' in line:
            current_file = 'replay.py'
        current_code.append(line)

print(f"Parsed {len(fixed_files)} fixed files: {list(fixed_files.keys())}\n")
print("=== Checks ===")
for fn in ['mutation.py', 'commit_graph.py', 'replay.py']:
    if fn in fixed_files:
        code = fixed_files[fn]
        # Accept either: removing random (return 1.0/True) or seeding random for determinism
        if fn == 'mutation.py':
            ok = ('return 1.0' in code and 'random.random()' not in code) or \
                 ('Random(' in code or 'seed' in code.lower())
        elif fn == 'commit_graph.py':
            ok = ('return True' in code and 'random.random()' not in code) or \
                 ('Random(' in code or 'seed' in code.lower())
        else:
            ok = 'synthetic' not in code or ('Random(' in code or 'seed' in code.lower())
        print(f"{'✓' if ok else '✗'} {fn}")
    else:
        print(f"✗ {fn} not provided")

# Run test
print("\n=== Running determinism test ===")
test_main = '''
class WAL:
    def __init__(self): self.log = []
    def append(self, e): self.log.append(e)
class Cache:
    def __init__(self): self.data = {}
    def get(self, uid): return self.data.get(uid, 0)
    def set(self, uid, val): self.data[uid] = val
class Ledger:
    def __init__(self): self.records = []
    def write(self, uid, amt): self.records.append((uid, amt))
'''
for fn in ['mutation', 'commit_graph', 'replay']:
    test_main += f'exec(open("{fn}.py").read())\n'
test_main += '''
def run_test():
    wal = WAL(); cache = Cache(); ledger = Ledger()
    m = MutationEngine(); c = CommitGraph(); seen = set()
    for i in range(50000):
        if not c.commit(): continue
        event = {"user_id": i % 2000, "amount": 1, "event_id": i}
        event["amount"] *= m.mutate_factor()
        tx_id = (event["user_id"], event["event_id"])
        if tx_id in seen: continue
        seen.add(tx_id)
        bal = cache.get(event["user_id"])
        cache.set(event["user_id"], bal + event["amount"])
        ledger.write(event["user_id"], event["amount"])
        wal.append(event)
    return {"ledger_size": len(ledger.records)}
r1 = run_test(); r2 = run_test()
print(f"Run 1: {r1}"); print(f"Run 2: {r2}")
print(f"Deterministic: {r1 == r2}")
'''
with tempfile.TemporaryDirectory() as tmpdir:
    for fn, code in fixed_files.items():
        (Path(tmpdir) / fn).write_text(code)
    (Path(tmpdir) / 'test_main.py').write_text(test_main)
    result = subprocess.run(['python3', 'test_main.py'], cwd=tmpdir, capture_output=True, text=True, timeout=300)
    print(result.stdout)
    if result.stderr:
        print(f"STDERR: {result.stderr[:200]}")
    if 'Deterministic: True' in result.stdout:
        print("✓ Successfully fixed non-determinism!")
    else:
        print("✗ Fix incomplete")
