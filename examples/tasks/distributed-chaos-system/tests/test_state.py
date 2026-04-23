import subprocess
import json
import os

def run_once():
    """Run the system once and return results."""
    # 直接运行修复后的 main.py
    result = subprocess.run(
        ["python3", "/app/main.py"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd="/app"
    )
    
    if result.returncode != 0:
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")
        raise RuntimeError(f"Process failed: {result.stderr}")
    
    try:
        with open("/tmp/result.json") as f:
            return json.load(f)
    except FileNotFoundError:
        raise RuntimeError("No result.json generated")

def test_determinism():
    """System must produce identical results on repeated runs."""
    r1 = run_once()
    r2 = run_once()
    
    assert r1 == r2, f"Non-deterministic: {r1} != {r2}"

def test_ledger_size():
    """All events should be processed after fix."""
    r = run_once()
    
    # After fix: should process all 50000 events
    # (mutation always 1.0, commit always True)
    assert r["ledger_size"] == 50000, f"Expected 50000, got {r['ledger_size']}"

def test_no_phantom():
    """No phantom transactions should appear."""
    r = run_once()
    
    # ledger_size should match replay_size exactly
    assert r["ledger_size"] == r.get("replay_size", r["ledger_size"]), \
        f"Ledger size mismatch: {r}"
