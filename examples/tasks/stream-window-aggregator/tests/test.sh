#!/usr/bin/env bash
# tests/test.sh — Verifier entry point
# Uploaded by harbor to /tests/test.sh inside the container.
# Writes final reward (0.0–1.0) to /logs/verifier/reward.txt.
set -uo pipefail

mkdir -p /logs/verifier

SCORES_FILE=/tmp/scores.json
REWARD=0.0

# ── Step 0: Generate input data and expected output (idempotent) ────────────
if [ ! -f /data/events.bin ]; then
    echo "[verifier] Generating input data..."
    python3 /solution/gen_data.py 2>&1 || {
        echo "[verifier] FATAL: failed to generate input data"
        echo "0.0" > /logs/verifier/reward.txt
        exit 0
    }
fi

if [ ! -f /data/expected.tsv ]; then
    echo "[verifier] Generating oracle expected output..."
    python3 /solution/oracle.py 2>&1 || {
        echo "[verifier] FATAL: failed to generate expected output"
        echo "0.0" > /logs/verifier/reward.txt
        exit 0
    }
fi

# ── Step 1: Run agent's aggregator if output not yet present ────────────────
if [ ! -f /data/output.tsv ]; then
    if [ -f /app/aggregator ]; then
        echo "[verifier] Running agent aggregator to produce /data/output.tsv..."
        timeout 90 /app/aggregator 2>&1 || echo "[verifier] aggregator exited non-zero or timed out"
    else
        echo "[verifier] /app/aggregator not found — skipping aggregator run"
    fi
fi

# ── Step 2: Measure peak RSS (write result for test_state.py to read) ───────
if [ -f /app/aggregator ] && [ -f /data/events.bin ]; then
    echo "[verifier] Measuring peak RSS..."
    RSS_KB=$(
        /usr/bin/time -v /app/aggregator 2>&1 1>/dev/null \
        | grep "Maximum resident set size" \
        | grep -o '[0-9]*$' || echo "0"
    )
    RSS_MB=$(python3 -c "print(int('${RSS_KB:-0}') / 1024)" 2>/dev/null || echo "999")
    echo "[verifier] Peak RSS: ${RSS_MB} MB (limit: 200 MB)"
    echo "$RSS_MB" > /tmp/rss_mb.txt
    python3 -c "print('1' if float('${RSS_MB}') < 200 else '0')" > /tmp/memory_ok.txt
fi

# ── Step 3: Run pytest checks ───────────────────────────────────────────────
echo "[verifier] Running pytest checks..."
python3 -m pytest /tests/test_state.py -v --tb=short -p no:cacheprovider \
    2>&1 | tee /logs/verifier/pytest.log || true

# ── Step 4: Read scores → reward ────────────────────────────────────────────
if [ -f "$SCORES_FILE" ]; then
    REWARD=$(python3 -c "
import json
with open('${SCORES_FILE}') as f:
    d = json.load(f)
r = max(0.0, min(1.0, float(d.get('total', 0.0))))
print(f'{r:.4f}')
" 2>/dev/null || echo "0.0")
else
    echo "[verifier] WARNING: ${SCORES_FILE} not found after pytest run"
    REWARD=0.0
fi

echo "[verifier] Final reward: $REWARD"
echo "$REWARD" > /logs/verifier/reward.txt
