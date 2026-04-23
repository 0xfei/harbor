#!/usr/bin/env bash
# tests/test.sh — Verifier for stream-ingest-deadlock
set -uo pipefail

mkdir -p /logs/verifier /app

# ── Step 0: Seed /app with base files ─────────────────────────────────────────
# 复制只读的基础文件
cp /tests/main.py   /app/main.py
cp /tests/dedup.py  /app/dedup.py
cp /tests/wal.py    /app/wal.py

# 如果 agent 没有写入 dispatcher.py，使用有 bug 的版本
if [ ! -f /app/dispatcher.py ]; then
    echo "[verifier] /app/dispatcher.py not found — using buggy baseline"
    cp /tests/dispatcher_buggy.py /app/dispatcher.py
fi

# 生成测试数据（如果不存在）
if [ ! -f /data/events.jsonl ] || [ ! -s /data/events.jsonl ]; then
    echo "[verifier] Generating test data..."
    python3 -c "
import json
with open('/data/events.jsonl', 'w') as f:
    for i in range(100000):
        evt = {'id': i, 'shard': i % 8, 'seq': i // 8}
        f.write(json.dumps(evt) + '\n')
"
fi

echo "[verifier] Running tests..."
cd /app

# 运行 pytest
pytest -q /tests/test_state.py 2>&1 | tee /logs/verifier/test_output.txt
EXIT_CODE=${PIPESTATUS[0]}

# 计算奖励
if [ "$EXIT_CODE" -eq 0 ]; then
    REWARD=1.0
else
    # 解析失败数
    FAIL_COUNT=$(grep -c 'FAILED' /logs/verifier/test_output.txt 2>/dev/null) || FAIL_COUNT=1
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
