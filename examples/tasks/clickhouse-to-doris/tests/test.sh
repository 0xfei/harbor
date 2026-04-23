#!/usr/bin/env bash
# tests/test.sh — Verifier for clickhouse-to-doris
set -uo pipefail

mkdir -p /logs/verifier

echo "[verifier] Checking service availability..."

# Check ClickHouse
if ! clickhouse-client --host clickhouse --query "SELECT 1" >/dev/null 2>&1; then
    echo "[verifier] ClickHouse not responding"
    echo "0.0" > /logs/verifier/reward.txt
    exit 0
fi

# Check Doris
if ! mysql -hdoris-fe -P9030 -uroot -e "SELECT 1" >/dev/null 2>&1; then
    echo "[verifier] Doris not responding"
    echo "0.0" > /logs/verifier/reward.txt
    exit 0
fi

echo "[verifier] Running verification tests..."

# Run Python verification
python3 /tests/verify_migration.py 2>&1 | tee /logs/verifier/test_output.txt
EXIT_CODE=${PIPESTATUS[0]}

if [ "$EXIT_CODE" -eq 0 ]; then
    echo "[verifier] All tests passed"
    echo "1.0" > /logs/verifier/reward.txt
else
    echo "[verifier] Some tests failed"
    # Calculate partial score based on passed tests
    PASSED=$(grep -c "✅" /logs/verifier/test_output.txt 2>/dev/null || echo "0")
    TOTAL=7
    REWARD=$(python3 -c "print(round($PASSED / $TOTAL, 4))")
    echo "$REWARD" > /logs/verifier/reward.txt
fi
