#!/bin/bash
# Run kimi-k2.5 multi-round optimization test

TASK_DIR="/Users/0x01f/harbor/examples/tasks/vector-search-optimization"

echo "=== Running Kimi-k2.5 Optimization Test ==="
echo ""

# Check API key
if [ -z "$BAILIAN_API_KEY" ]; then
    echo "ERROR: BAILIAN_API_KEY not set"
    echo "Please set it: export BAILIAN_API_KEY='your-key-here'"
    exit 1
fi

# Run test
cd "$TASK_DIR/tests" && python3 test_kimi_optimization.py

echo ""
echo "Results saved to: $TASK_DIR/results/kimi_multi_round.json"
