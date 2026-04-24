#!/usr/bin/env bash
# Comprehensive test runner with anti-cheat verification
# Forces execution of ALL tests and records timestamps

set -euo pipefail

# Verify environment
: "${KIMI_API_KEY:?KIMI_API_KEY must be set}"
: "${KIMI_URL:?KIMI_URL must be set}"
: "${KIMI_MODEL:?KIMI_MODEL must be set}"

# Configuration
MAX_TEST_TIMEOUT=300  # 5 minutes per test
API_TIMEOUT=60         # 1 minute for single API call

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
RESULTS_FILE="TEST_RESULTS.md"
LOG_FILE="test_execution.log"

# Clear previous results
: > "$LOG_FILE"

cat > "$RESULTS_FILE" << EOF
# Harbor 测试结果 - 最新运行

> **执行时间**: $TIMESTAMP
> **模型**: $KIMI_MODEL  
> **API**: $KIMI_URL
> **API密钥前缀**: ${KIMI_API_KEY:0:12}...

---

## 强制执行测试（防止绕过）

EOF

# Anti-cheat: Verify API connectivity first
echo "### API连接验证" >> "$RESULTS_FILE"
echo "" >> "$RESULTS_FILE"
echo '```' >> "$RESULTS_FILE"
echo "测试时间: $(date '+%H:%M:%S')" >> "$RESULTS_FILE"

python3 -c "
import sys
sys.path.insert(0, 'examples/tasks')
from kimi_client import call_kimi, KIMI_MODEL
import time
start = time.time()
try:
    r = call_kimi([{'role':'user','content':'Ping'}], max_tokens=10, timeout=30)
    elapsed = time.time() - start
    print(f'✅ API连接成功 ({elapsed:.1f}s)')
    print(f'响应: {r[:50]}...')
except Exception as e:
    print(f'❌ API连接失败: {e}')
    sys.exit(1)
" | tee -a "$RESULTS_FILE"

if [ ${PIPESTATUS[0]} -ne 0 ]; then
    echo '```' >> "$RESULTS_FILE"
    echo "" >> "$RESULTS_FILE"
    echo "**停止测试：API连接失败**" >> "$RESULTS_FILE"
    cat "$RESULTS_FILE"
    exit 1
fi

echo '```' >> "$RESULTS_FILE"
echo "" >> "$RESULTS_FILE"

# Test execution function
run_test() {
    local name="$1"
    local script="$2"
    local start end elapsed
    
    echo "### $name" >> "$RESULTS_FILE"
    echo "" >> "$RESULTS_FILE"
    echo '```' >> "$RESULTS_FILE"
    
    start=$SECONDS
    echo "[$(date '+%H:%M:%S')] 开始执行: $name" | tee -a "$LOG_FILE"
    
    if python3 "$script" >> "$LOG_FILE" 2>&1; then
        end=$SECONDS
        elapsed=$((end - start))
        echo "[$(date '+%H:%M:%S')] ✅ PASS (${elapsed}s)" | tee -a "$LOG_FILE"
        echo "开始: $(date -r $start '+%H:%M:%S' 2>/dev/null || date '+%H:%M:%S')" >> "$RESULTS_FILE"
        echo "结束: $(date '+%H:%M:%S')" >> "$RESULTS_FILE"
        echo "耗时: ${elapsed}秒" >> "$RESULTS_FILE"
        echo "状态: ✅ PASS" >> "$RESULTS_FILE"
    else
        end=$SECONDS
        elapsed=$((end - start))
        echo "[$(date '+%H:%M:%S')] ❌ FAIL (${elapsed}s)" | tee -a "$LOG_FILE"
        echo "开始: $(date -r $start '+%H:%M:%S' 2>/dev/null || date '+%H:%M:%S')" >> "$RESULTS_FILE"
        echo "结束: $(date '+%H:%M:%S')" >> "$RESULTS_FILE"
        echo "耗时: ${elapsed}秒" >> "$RESULTS_FILE"
        echo "状态: ❌ FAIL" >> "$RESULTS_FILE"
        echo "错误: 查看test_execution.log" >> "$RESULTS_FILE"
    fi
    
    echo '```' >> "$RESULTS_FILE"
    echo "" >> "$RESULTS_FILE"
}

echo "## 静态分析测试" >> "$RESULTS_FILE"
echo "" >> "$RESULTS_FILE"

run_test "kafka2clickhouse-debug" "examples/tasks/kafka2clickhouse-debug/tests/test_kimi_debug.py"
run_test "clickhouse-mergetree-debug" "examples/tasks/clickhouse-mergetree-debug/tests/test_kimi_debug.py"
run_test "clickhouse-to-doris" "examples/tasks/clickhouse-to-doris/tests/test_kimi_migration.py"
run_test "distributed-chaos-system" "examples/tasks/distributed-chaos-system/test_kimi.py"
run_test "storage-performance-analysis" "examples/tasks/storage-performance-analysis/tests/test_kimi_analysis.py"

# Oracle/Nop tests (shorter versions)
echo "## Harbor Oracle/Nop 验证" >> "$RESULTS_FILE"
echo "" >> "$RESULTS_FILE"

for task in kafka2clickhouse-debug clickhouse-mergetree-debug storage-performance-analysis; do
    echo "#### $task" >> "$RESULTS_FILE"
    echo "" >> "$RESULTS_FILE"
    for agent in oracle nop; do
        echo "##### $agent" >> "$RESULTS_FILE"
        echo '```' >> "$RESULTS_FILE"
        start=$SECONDS
        echo "[$(date '+%H:%M:%S')] $task/$agent 开始" | tee -a "$LOG_FILE"
        
        if uv run harbor run -a "$agent" -p "examples/tasks/$task" >> "$LOG_FILE" 2>&1; then
            elapsed=$((SECONDS - start))
            echo "[$(date '+%H:%M:%S')] ✅ (${elapsed}s)" | tee -a "$LOG_FILE"
            echo "状态: ✅ PASS (${elapsed}s)" >> "$RESULTS_FILE"
        else
            elapsed=$((SECONDS - start))
            echo "[$(date '+%H:%M:%S')] ❌ (${elapsed}s)" | tee -a "$LOG_FILE"
            echo "状态: ❌ FAIL (${elapsed}s)" >> "$RESULTS_FILE"
        fi
        echo '```' >> "$RESULTS_FILE"
        echo "" >> "$RESULTS_FILE"
    done
done

# Final summary
cat >> "$RESULTS_FILE" << EOF

---

## 执行汇总

- **总运行时间**: $TIMESTAMP 至 $(date '+%Y-%m-%d %H:%M:%S')
- **详细日志**: test_execution.log
- **结果文件**: TEST_RESULTS.md

---

*由 run_comprehensive_tests.sh 自动生成*
*每个测试都强制执行并记录时间戳*
EOF

echo ""
echo "=== 测试执行完成 ==="
echo "结果文件: $RESULTS_FILE"
echo "详细日志: $LOG_FILE"
cat "$RESULTS_FILE"
