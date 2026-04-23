#!/usr/bin/env bash
# tests/test.sh — Verifier for distributed-chaos-system
set -uo pipefail

mkdir -p /logs/verifier /data

# 生成测试数据（如果不存在）
if [ ! -f /data/events.jsonl ] || [ ! -s /data/events.jsonl ]; then
    echo "[verifier] Generating test data..."
    python3 -c "
import json, random
random.seed(42)
with open('/data/events.jsonl', 'w') as f:
    for i in range(50000):
        f.write(json.dumps({
            'user_id': i % 2000,
            'amount': 1,
            'event_id': i,
            'timestamp': i // 5,
            'source': 'A'
        }) + '\n')
"
fi

# 如果 app 目录为空，从 tests/app 复制
if [ ! -f /app/main.py ]; then
    echo "[verifier] Seeding /app..."
    cp -r /tests/app/* /app/ 2>/dev/null || true
fi

echo "[verifier] Running tests..."
cd /app
export PYTHONPATH=/app

pytest -q /tests/test_state.py 2>&1 | tee /logs/verifier/test_output.txt
EXIT_CODE=${PIPESTATUS[0]}

# Calculate reward
if [ "$EXIT_CODE" -eq 0 ]; then
    REWARD=1.0
else
    FAIL_COUNT=$(grep -c 'FAILED' /logs/verifier/test_output.txt 2>/dev/null) || FAIL_COUNT=3
    PASS_COUNT=$(grep -c 'PASSED' /logs/verifier/test_output.txt 2>/dev/null) || PASS_COUNT=0
    TOTAL=$((PASS_COUNT + FAIL_COUNT))
    if [ "$TOTAL" -gt 0 ]; then
        REWARD=$(python3 -c "print(round($PASS_COUNT / $TOTAL, 4))") || REWARD=0.0
    else
        REWARD=0.0
    fi
fi

echo "[verifier] Final reward: $REWARD"
echo "$REWARD" > /logs/verifier/reward.txt
