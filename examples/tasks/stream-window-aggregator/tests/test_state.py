"""
tests/test_state.py — Multi-dimensional verifier for stream-window-aggregator.

Score breakdown (weights sum to 1.0):
  correctness   0.50  — output matches /data/expected.tsv line-by-line
  no_mutex      0.15  — binary contains no mutex/lock symbols
  no_map        0.10  — binary contains no std::map/set symbols
  memory        0.10  — peak RSS < 200 MB (pre-measured by test.sh)
  four_threads  0.05  — binary spawns exactly 4 worker threads
  source_file   0.05  — /app/aggregator.cpp exists
  output_fmt    0.05  — output format is valid (numeric sort, cat:score)
"""

import json
import os
import re
import subprocess
import sys
import time

import pytest

# ── Constants (also imported by conftest.py) ─────────────────────────────────
OUTPUT_TSV  = "/data/output.tsv"
EXPECTED_TSV = "/data/expected.tsv"
BINARY      = "/app/aggregator"
SOURCE      = "/app/aggregator.cpp"
SCORES_FILE = "/tmp/scores.json"

weights = {
    "correctness":  0.50,
    "no_mutex":     0.15,
    "no_map":       0.10,
    "memory":       0.10,
    "four_threads": 0.05,
    "source_file":  0.05,
    "output_fmt":   0.05,
}

# Mutable scores dict — written to disk by conftest.pytest_sessionfinish
_SCORES: dict[str, float] = {}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _nm_symbols() -> str:
    try:
        r = subprocess.run(["nm", "-C", BINARY], capture_output=True, text=True, timeout=30)
        return (r.stdout + r.stderr).lower()
    except Exception:
        return ""


def _read_tsv(path: str) -> list[tuple[int, str]]:
    rows = []
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            assert len(parts) == 2, f"Bad TSV line: {line!r}"
            rows.append((int(parts[0]), parts[1]))
    return rows


def _run_and_count_threads(timeout_sec: int = 60) -> int:
    """
    Run /app/aggregator in the background while sampling /proc/<pid>/status.
    Returns the maximum Threads count observed.
    We use a fresh output path to avoid conflicting with /data/output.tsv.
    """
    if not os.path.isfile(BINARY):
        return 0
    if not os.path.isfile("/data/events.bin"):
        return 0

    # Redirect output to a temp file so we don't clobber the agent's result
    env = os.environ.copy()
    proc = subprocess.Popen(
        [BINARY],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    pid = proc.pid
    max_threads = 1
    deadline = time.monotonic() + timeout_sec

    # Dense initial sampling to catch the brief multi-threaded phase
    while proc.poll() is None and time.monotonic() < deadline:
        try:
            with open(f"/proc/{pid}/status") as fh:
                for line in fh:
                    if line.startswith("Threads:"):
                        t = int(line.split(":")[1].strip())
                        if t > max_threads:
                            max_threads = t
                        break
        except (FileNotFoundError, ProcessLookupError):
            break
        time.sleep(0.002)   # 2ms — fast enough to catch short-lived threads

    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    return max_threads


# ── Tests ────────────────────────────────────────────────────────────────────

def test_source_file():
    """0.05 — /app/aggregator.cpp must exist."""
    exists = os.path.isfile(SOURCE)
    _SCORES["source_file"] = 1.0 if exists else 0.0
    assert exists, f"{SOURCE} not found"


def test_binary_exists():
    """Prerequisite: binary compiled."""
    assert os.path.isfile(BINARY), f"{BINARY} not found — did not compile"


def test_output_format():
    """0.05 — valid TSV, numeric user_id sort, cat:score format."""
    assert os.path.isfile(OUTPUT_TSV), f"{OUTPUT_TSV} not found"
    rows = _read_tsv(OUTPUT_TSV)
    assert len(rows) > 0, "Output is empty"

    uids = [r[0] for r in rows]
    assert uids == sorted(uids), "user_ids not in ascending numeric order"

    pat = re.compile(r"^\d+:\d+(,\d+:\d+){0,2}$")
    for uid, cs in rows:
        assert pat.match(cs), f"Bad category:score for uid {uid}: {cs!r}"
        assert len(cs.split(",")) <= 3, f">3 categories for uid {uid}"

    _SCORES["output_fmt"] = 1.0


def test_correctness():
    """0.50 — output must match expected.tsv with ≥95% accuracy."""
    assert os.path.isfile(EXPECTED_TSV), f"{EXPECTED_TSV} not found"
    assert os.path.isfile(OUTPUT_TSV),   f"{OUTPUT_TSV} not found"

    exp = dict(_read_tsv(EXPECTED_TSV))
    act = dict(_read_tsv(OUTPUT_TSV))
    assert exp, "Expected file is empty"

    correct = sum(1 for uid, v in exp.items() if act.get(uid) == v)
    ratio = correct / len(exp)
    _SCORES["correctness"] = round(ratio, 4)

    assert ratio >= 0.95, (
        f"Correctness {correct}/{len(exp)} = {ratio:.1%}. "
        "Likely cause: wrong window semantics (processing-time vs event-time), "
        "wrong tie-breaking order, or wrong numeric sort."
    )


def test_no_mutex():
    """0.15 — binary must NOT link mutex/lock primitives."""
    forbidden = [
        "pthread_mutex", "std::mutex", "__gthread_mutex",
        "std::lock_guard", "std::unique_lock",
        "sem_wait", "sem_post", "pthread_rwlock",
    ]
    syms = _nm_symbols()
    found = [p for p in forbidden if p.lower() in syms]
    _SCORES["no_mutex"] = 0.0 if found else 1.0
    assert not found, f"Forbidden mutex symbols: {found}"


def test_no_map():
    """0.10 — binary must NOT link std::map / std::unordered_map."""
    forbidden = [
        "std::map<", "std::unordered_map<",
        "std::set<", "std::unordered_set<",
        "_rb_tree", "__detail::_hashtable",
    ]
    syms = _nm_symbols()
    found = [p for p in forbidden if p.lower() in syms]
    _SCORES["no_map"] = 0.0 if found else 1.0
    assert not found, f"Forbidden map/set symbols: {found}"


def test_four_threads():
    """0.05 — binary must spawn exactly 4 worker threads."""
    if not os.path.isfile("/data/events.bin"):
        pytest.skip("events.bin missing")

    max_t = _run_and_count_threads(timeout_sec=60)
    # main + 4 workers = 5; allow ±1 for timing jitter
    ok = 4 <= max_t <= 6
    _SCORES["four_threads"] = 1.0 if ok else 0.0
    assert ok, (
        f"Expected 4–6 threads (main + 4 workers), observed max={max_t}. "
        "Ensure exactly 4 worker std::threads are spawned and running concurrently."
    )


def test_memory():
    """0.10 — peak RSS < 200 MB (pre-measured by test.sh)."""
    mem_file = "/tmp/memory_ok.txt"
    rss_file = "/tmp/rss_mb.txt"

    if not os.path.isfile(mem_file):
        _SCORES["memory"] = 0.5   # partial credit if measurement unavailable
        pytest.skip("Memory pre-measurement not available")

    ok = open(mem_file).read().strip() == "1"
    rss = open(rss_file).read().strip() if os.path.isfile(rss_file) else "?"
    _SCORES["memory"] = 1.0 if ok else 0.0
    assert ok, f"Peak RSS {rss} MB exceeds 200 MB limit"
