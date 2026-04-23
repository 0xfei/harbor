#!/usr/bin/env bash
# tests/test.sh — Verifier for bitmap-vector-fix
# Seeds /app with read-only base files, then compiles and runs tests.
set -uo pipefail

mkdir -p /logs/verifier

REWARD=0.0
TEST_BIN=/app/bitmap_manager_test

# ── Step 0: Seed /app with read-only base files ───────────────────────────────
cp /tests/bitmap.h                /app/bitmap.h
cp /tests/hash.h                  /app/hash.h
cp /tests/bitmap_manager.h        /app/bitmap_manager.h
cp /tests/bitmap_manager_test.cpp /app/bitmap_manager_test.cpp

# If agent/oracle hasn't written bitmap_manager.cpp, fallback to buggy version.
if [ ! -f /app/bitmap_manager.cpp ]; then
    echo "[verifier] /app/bitmap_manager.cpp not found — using buggy baseline"
    cp /tests/bitmap_manager_buggy.cpp /app/bitmap_manager.cpp
fi

# ── Step 1: Compile ───────────────────────────────────────────────────────────
echo "[verifier] Compiling..."
if ! g++ -std=c++11 -o "$TEST_BIN" \
         /app/bitmap_manager_test.cpp \
         /app/bitmap_manager.cpp 2>/logs/verifier/compile.log; then
    echo "[verifier] Compilation failed:"
    cat /logs/verifier/compile.log
    echo "0.0" > /logs/verifier/reward.txt
    exit 0
fi

# ── Step 2: Run tests ─────────────────────────────────────────────────────────
echo "[verifier] Running tests..."
"$TEST_BIN" 2>&1 | tee /logs/verifier/test_output.txt
EXIT_CODE=${PIPESTATUS[0]}

# ── Step 3: Parse results ─────────────────────────────────────────────────────
# Use grep without -c to avoid exit code issues, then count lines
FAIL_COUNT=$(grep '^\s*\[FAIL\]' /logs/verifier/test_output.txt 2>/dev/null | wc -l | tr -d ' ')
PASS_COUNT=$(grep '^\s*\[PASS\]' /logs/verifier/test_output.txt 2>/dev/null | wc -l | tr -d ' ')
TOTAL=$((PASS_COUNT + FAIL_COUNT))

echo "[verifier] PASS=$PASS_COUNT FAIL=$FAIL_COUNT exit=$EXIT_CODE"

if [ "$EXIT_CODE" -eq 0 ] && [ "$FAIL_COUNT" -eq 0 ]; then
    REWARD=1.0
elif [ "$TOTAL" -gt 0 ]; then
    REWARD=$(python3 -c "print(round($PASS_COUNT / $TOTAL, 4))" 2>/dev/null || echo "0.0")
fi

echo "[verifier] Final reward: $REWARD"
echo "$REWARD" > /logs/verifier/reward.txt
