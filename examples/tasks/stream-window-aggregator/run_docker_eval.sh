#!/usr/bin/env bash
# run_docker_eval.sh — 用 Harbor 容器真实编译并运行 kimi-k2.5 生成的代码
# 用法: bash run_docker_eval.sh [cpp_file]
set -uo pipefail

TASK_DIR="$(cd "$(dirname "$0")" && pwd)"
CPP_FILE="${1:-${TASK_DIR}/eval_logs/run_1_code.cpp}"

if [ ! -f "$CPP_FILE" ]; then
    echo "❌ 未找到 cpp 文件: $CPP_FILE"
    exit 1
fi

echo "🐳 使用 Harbor 容器真实评测: $(basename $CPP_FILE)"

# 创建临时 agent 脚本，把 kimi 代码编译并运行
AGENT_SOLVE="$(mktemp /tmp/docker_agent_XXXXXX.sh)"
cat > "$AGENT_SOLVE" << AGENT_EOF
#!/usr/bin/env bash
set -uo pipefail
echo "[agent] Copying source file to /app/aggregator.cpp..."
# Harbor 会把 /solution/ 上传; 我们在 solve.sh 里放代码
cp /solution/kimi_code.cpp /app/aggregator.cpp
echo "[agent] Compiling..."
g++ -O2 -std=c++17 -pthread -o /app/aggregator /app/aggregator.cpp 2>&1
echo "[agent] Compilation done."
AGENT_EOF
chmod +x "$AGENT_SOLVE"
echo "Agent script: $AGENT_SOLVE"

# 把 kimi 代码复制到 solution/ 下，重命名为 kimi_code.cpp
cp "$CPP_FILE" "${TASK_DIR}/solution/kimi_code.cpp"

# 临时替换 solve.sh 用 kimi 代码
ORIG_SOLVE="${TASK_DIR}/solution/solve.sh"
BACKUP_SOLVE="${TASK_DIR}/solution/solve.sh.bak"
cp "$ORIG_SOLVE" "$BACKUP_SOLVE"

cat > "$ORIG_SOLVE" << 'SOLVE_EOF'
#!/usr/bin/env bash
set -uo pipefail
echo "[kimi-agent] Generating input data..."
python3 /solution/gen_data.py
echo "[kimi-agent] Compiling kimi-k2.5 code..."
cp /solution/kimi_code.cpp /app/aggregator.cpp
g++ -O2 -std=c++17 -pthread -o /app/aggregator /app/aggregator.cpp 2>&1
if [ $? -ne 0 ]; then
    echo "[kimi-agent] COMPILATION FAILED"
    exit 1
fi
echo "[kimi-agent] Running aggregator..."
/app/aggregator
echo "[kimi-agent] Done."
SOLVE_EOF
chmod +x "$ORIG_SOLVE"

echo ""
echo "🚀 运行 harbor run -a oracle (实际跑 kimi 代码)..."
cd /Users/0x01f/harbor
uv run harbor run -a oracle -p examples/tasks/stream-window-aggregator --no-delete 2>&1

# 恢复原始 solve.sh
cp "$BACKUP_SOLVE" "$ORIG_SOLVE"
rm -f "$BACKUP_SOLVE" "${TASK_DIR}/solution/kimi_code.cpp" "$AGENT_SOLVE"

echo ""
echo "✅ 评测完成，查看最新 jobs/ 目录获取详情"
