#!/usr/bin/env bash
# Run all kimi tests with proper timeout handling
# Max test duration: 5 minutes, API timeout: 1 minute

set -euo pipefail

# Verify environment
if [ -z "${KIMI_API_KEY:-}" ]; then
    echo "ERROR: KIMI_API_KEY not set"
    echo "Please add to ~/.zshrc: export KIMI_API_KEY='your-key'"
    exit 1
fi

echo "Model: $KIMI_MODEL"
echo "URL: $KIMI_URL"
echo "Max timeout: 300s per test, 60s per API call"
echo ""

# Function to run test with timeout
run_test() {
    local name="$1"
    local script="$2"
    local start elapsed
    
    echo "--- $name ---"
    start=$SECONDS
    
    # Run with 5min timeout using background process
    python3 "$script" &
    local pid=$!
    
    # Wait up to 300 seconds
    local count=0
    while [ $count -lt 300 ]; do
        if ! kill -0 $pid 2>/dev/null; then
            wait $pid
            elapsed=$((SECONDS - start))
            echo "✅ PASS (${elapsed}s)"
            echo ""
            return 0
        fi
        sleep 1
        count=$((count + 1))
    done
    
    # Timeout - kill process
    kill $pid 2>/dev/null || true
    wait $pid 2>/dev/null || true
    elapsed=$((SECONDS - start))
    echo "❌ TIMEOUT (${elapsed}s)"
    echo ""
    return 1
}

# Run all tests
run_test "kafka2clickhouse-debug"        "examples/tasks/kafka2clickhouse-debug/tests/test_kimi_debug.py"
run_test "clickhouse-mergetree-debug"    "examples/tasks/clickhouse-mergetree-debug/tests/test_kimi_debug.py"
run_test "clickhouse-to-doris"           "examples/tasks/clickhouse-to-doris/tests/test_kimi_migration.py"
run_test "distributed-chaos-system"      "examples/tasks/distributed-chaos-system/test_kimi.py"
run_test "storage-performance-analysis"  "examples/tasks/storage-performance-analysis/tests/test_kimi_analysis.py"

echo "=== All tests complete ==="
