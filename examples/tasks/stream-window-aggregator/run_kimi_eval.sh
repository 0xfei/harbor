#!/usr/bin/env bash
# run_kimi_eval.sh — 调用阿里云 Bailian API 测试 kimi-k2.5 模型解题成功率
#
# 用法:
#   bash run_kimi_eval.sh [RUNS]
#   RUNS: 运行次数，默认 5
#
# 前提: 环境变量 BAILIAN_API_KEY 已设置
# 依赖: curl, python3
# 模型: kimi-k2.5  (阿里云 Bailian 兼容接口)

set -euo pipefail

# ── 配置 ─────────────────────────────────────────────────────────────────────
API_BASE="https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL="kimi-k2.5"
RUNS="${1:-5}"
TASK_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTRUCTION_FILE="${TASK_DIR}/instruction.md"
LOG_DIR="${TASK_DIR}/eval_logs"
RESULTS_FILE="${LOG_DIR}/results.jsonl"

# ── 前置检查 ──────────────────────────────────────────────────────────────────
if [[ -z "${BAILIAN_API_KEY:-}" ]]; then
    echo "❌  环境变量 BAILIAN_API_KEY 未设置" >&2
    echo "    请先执行: export BAILIAN_API_KEY=sk-xxxx" >&2
    exit 1
fi

if [[ ! -f "$INSTRUCTION_FILE" ]]; then
    echo "❌  找不到 instruction.md: $INSTRUCTION_FILE" >&2
    exit 1
fi

if ! command -v python3 &>/dev/null; then
    echo "❌  python3 未安装" >&2
    exit 1
fi

mkdir -p "$LOG_DIR"

# ── 内联 Python 评分脚本（写入临时文件，通过 stdin 接收代码）────────────────
SCORER_PY="${LOG_DIR}/_scorer.py"
cat > "$SCORER_PY" << 'PYEOF'
#!/usr/bin/env python3
"""
静态评分器：从 stdin 读取 C++ 代码，输出 JSON 分数。

维度权重（与 test_state.py 对齐）：
  correctness_hint  0.40  — 两遍扫描逻辑（先找 max_ts，再按事件时间聚合）
  constraint_a      0.20  — 未使用 mutex/lock_guard（只用 atomic）
  constraint_b      0.15  — 未使用 std::map/unordered_map
  constraint_e      0.10  — 恰好 4 个工作线程
  compilation_hint  0.10  — 有 #include 和 main() 函数体
  format_hint       0.05  — 输出到 /data/output.tsv，格式正确
"""
import sys, re, json

code = sys.stdin.read()

def has(pattern):
    return bool(re.search(pattern, code, re.IGNORECASE | re.DOTALL))

scores = {}

# correctness_hint: 两遍扫描 —— 先全量扫一遍确定 max_ts，再按 event_ts_ms 过滤
# 关键特征：存在 max_ts 相关变量，且有 event-time 窗口比较
has_max_ts    = has(r'\bmax_ts\b')
has_two_pass  = has(r'pass.{0,5}[12]|second.pass|phase.{0,5}[12]|accumulate|window.start|event_ts.*>=.*max_ts|max_ts.*-.*\b30')
has_event_cmp = has(r'event_ts_ms\s*[><=!]|\.event_ts_ms')
scores["correctness_hint"] = 1.0 if (has_max_ts and (has_two_pass or has_event_cmp)) else 0.0

# constraint_a: 没用锁
mutex_used = has(r'std\s*::\s*mutex\b|lock_guard|unique_lock|pthread_mutex|sem_wait|sem_post|pthread_rwlock')
scores["constraint_a"] = 0.0 if mutex_used else 1.0

# constraint_b: 没用 map/set
map_used = has(r'std\s*::\s*(unordered_)?map\s*<|std\s*::\s*(unordered_)?set\s*<|_rb_tree|_hashtable')
scores["constraint_b"] = 0.0 if map_used else 1.0

# constraint_e: 恰好 4 个线程
has_4_threads = (
    has(r'\bN_THREADS\s*=\s*4\b') or
    has(r'std\s*::\s*thread\s+\w+\s*\[\s*4\s*\]') or
    has(r'for\s*\(.*[^0-9]4[^0-9].*thread') or
    (has(r'\bstd\s*::\s*thread\b') and has(r'\b4\b') and has(r'\.join\(\)'))
)
scores["constraint_e"] = 1.0 if has_4_threads else 0.0

# compilation_hint: 有 #include 和 main
has_main    = has(r'\bint\s+main\s*\(')
has_include = has(r'#include\s*<(cstdint|cstdio|thread|atomic|algorithm)')
has_atomic  = has(r'std\s*::\s*atomic|fetch_add|compare_exchange|atomic_ref')
scores["compilation_hint"] = (
    1.0 if (has_main and has_include and has_atomic) else
    0.5 if (has_main and has_include) else
    0.2 if has_main else 0.0
)

# format_hint: 输出路径和格式
has_output_path = has(r'/data/output\.tsv|output\.tsv')
has_tab_sep     = has(r'\\t|\\047|"\t"|\bputchar\s*\(\s*9\s*\)|\bfputc\s*\(.*\\t')
scores["format_hint"] = 1.0 if has_output_path else (0.5 if has_tab_sep else 0.0)

weights = {
    "correctness_hint": 0.40,
    "constraint_a":     0.20,
    "constraint_b":     0.15,
    "constraint_e":     0.10,
    "compilation_hint": 0.10,
    "format_hint":      0.05,
}
total = sum(weights[k] * scores[k] for k in weights)
scores["total"] = round(total, 4)
print(json.dumps(scores))
PYEOF

# ── 内联 API 请求脚本（写入临时文件，接收 run_id 参数）───────────────────────
CALLER_PY="${LOG_DIR}/_caller.py"
cat > "$CALLER_PY" << PYEOF2
#!/usr/bin/env python3
"""
负责构造 JSON 请求体、调用 API、将响应写入 log 文件，
并把提取出的代码内容输出到 stdout。
"""
import json, sys, os, urllib.request, urllib.error

run_id       = sys.argv[1]
log_dir      = sys.argv[2]
api_base     = sys.argv[3]
model        = sys.argv[4]
api_key      = sys.argv[5]
task_content = open(sys.argv[6]).read()

prompt = (
    "You are an expert C++ systems programmer. Solve the following programming task completely.\n"
    "Output ONLY the C++ source code for /app/aggregator.cpp.\n"
    "Do NOT include markdown code fences, explanations, or any text outside the C++ code itself.\n\n"
    "---\n" + task_content + "\n---"
)

body = {
    "model": model,
    "messages": [
        {"role": "system", "content": "You are an expert C++17 systems programmer. Output only raw, compilable C++ code — no markdown, no explanation."},
        {"role": "user",   "content": prompt}
    ],
    "temperature": 0.2,
    "max_tokens": 8192,
}

req = urllib.request.Request(
    f"{api_base}/chat/completions",
    data=json.dumps(body).encode("utf-8"),
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    },
    method="POST",
)

log_file  = os.path.join(log_dir, f"run_{run_id}.json")
code_file = os.path.join(log_dir, f"run_{run_id}_code.cpp")

try:
    with urllib.request.urlopen(req, timeout=180) as resp:
        raw = resp.read().decode("utf-8")
except urllib.error.HTTPError as e:
    raw = e.read().decode("utf-8", errors="replace")
    with open(log_file, "w") as f:
        f.write(raw)
    print(json.dumps({"error": True, "http_error": e.code, "total": 0.0}))
    sys.exit(0)
except Exception as e:
    with open(log_file, "w") as f:
        f.write(str(e))
    print(json.dumps({"error": True, "exception": str(e), "total": 0.0}))
    sys.exit(0)

with open(log_file, "w") as f:
    f.write(raw)

try:
    d = json.loads(raw)
    content = d["choices"][0]["message"]["content"]
except Exception as e:
    print(json.dumps({"error": True, "parse_failed": True, "detail": str(e), "total": 0.0}))
    sys.exit(0)

# 去掉可能存在的 markdown 代码围栏
import re
content = re.sub(r"^\s*\`\`\`[a-zA-Z+]*\s*\n?", "", content)
content = re.sub(r"\n?\`\`\`\s*$", "", content)

with open(code_file, "w") as f:
    f.write(content)

# 把代码写到 stdout 供评分器读取
sys.stdout.write(content)
PYEOF2

# ── API 调用 + 评分函数 ────────────────────────────────────────────────────────
call_and_score() {
    local run_id="$1"

    echo "  → 正在请求 API [run ${run_id}/${RUNS}] ..." >&2

    # 调用 API，把代码通过 stdout 管道送给评分器
    local scores_json
    scores_json=$(python3 "$CALLER_PY" \
                    "$run_id" "$LOG_DIR" "$API_BASE" "$MODEL" \
                    "$BAILIAN_API_KEY" "$INSTRUCTION_FILE" \
                  | python3 "$SCORER_PY")

    echo "$scores_json"
}

# ── 主循环 ────────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
printf "║  Kimi K2.5 评测  %-45s║\n" "— stream-window-aggregator"
printf "║  模型: %-56s║\n" "$MODEL"
printf "║  API:  %-56s║\n" "$API_BASE"
printf "║  轮数: %-56s║\n" "$RUNS"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

# 清空旧结果
> "$RESULTS_FILE"

declare -a all_totals=()
success_count=0   # total >= 0.7 视为"通过"

for i in $(seq 1 "$RUNS"); do
    echo "▶ Run ${i}/${RUNS}"
    result=$(call_and_score "$i") || result='{"error":true,"total":0}'

    # 写入 jsonl（带 run_id）
    python3 -c "
import json, sys
d = json.loads(sys.argv[1])
d['run_id'] = int(sys.argv[2])
print(json.dumps(d))
" "$result" "$i" >> "$RESULTS_FILE" 2>/dev/null || echo "{\"run_id\":$i,\"error\":true,\"total\":0}" >> "$RESULTS_FILE"

    # 解析分数
    total=$(python3 -c "
import json, sys
try:
    print(json.loads(sys.argv[1]).get('total', 0))
except:
    print(0)
" "$result" 2>/dev/null || echo "0")

    all_totals+=("$total")

    # 各维度展示
    details=$(python3 -c "
import json, sys
try:
    d = json.loads(sys.argv[1])
    keys = [
        ('correctness_hint', 'EventTime'),
        ('constraint_a',     'NoMutex'),
        ('constraint_b',     'NoMap'),
        ('constraint_e',     '4Threads'),
        ('compilation_hint', 'Compiles'),
        ('format_hint',      'Format'),
    ]
    parts = []
    for k, label in keys:
        v = d.get(k, -1)
        if v == 1.0:   icon = '\033[32m✓\033[0m'
        elif v == 0.0: icon = '\033[31m✗\033[0m'
        else:          icon = '\033[33m~\033[0m'
        parts.append(f'{icon}{label}')
    print('  '.join(parts))
except:
    print('  (解析失败)')
" "$result" 2>/dev/null || echo "  (解析失败)")

    # 是否通过
    pass_flag=$(python3 -c "
t = float('$total')
print('\033[32mPASS ✅\033[0m' if t >= 0.7 else '\033[31mFAIL ❌\033[0m')
" 2>/dev/null || echo "FAIL ❌")
    [[ "$pass_flag" == *"PASS"* ]] && ((success_count++)) || true

    printf "  Score: \033[1m%.4f\033[0m  %b\n" "$total" "$pass_flag"
    echo -e "  Dims:  $details"
    echo "  Log:   ${LOG_DIR}/run_${i}.json  |  Code: ${LOG_DIR}/run_${i}_code.cpp"
    echo ""
done

# ── 汇总统计 ──────────────────────────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 汇总统计  (模型: ${MODEL},  共 ${RUNS} 轮)"
echo ""

python3 - "$RUNS" "$success_count" "${all_totals[@]}" << 'STATSEOF'
import sys, statistics, json

runs    = int(sys.argv[1])
success = int(sys.argv[2])
totals  = [float(x) for x in sys.argv[3:] if x]

if not totals:
    print("  无有效数据")
    sys.exit(0)

avg   = statistics.mean(totals)
med   = statistics.median(totals)
stdev = statistics.stdev(totals) if len(totals) > 1 else 0.0
mn    = min(totals)
mx    = max(totals)
rate  = success / runs * 100

# 进度条
W      = 40
filled = int(rate / 100 * W)
bar    = "█" * filled + "░" * (W - filled)

print(f"  成功率 (score≥0.7): {success}/{runs} = {rate:.1f}%")
print(f"  [{bar}] {rate:.1f}%")
print()
print(f"  平均分:    {avg:.4f}")
print(f"  中位数:    {med:.4f}")
print(f"  标准差:    {stdev:.4f}")
print(f"  最低/最高: {mn:.4f} / {mx:.4f}")
print()

for idx, t in enumerate(totals, 1):
    bar_w = int(t * 20)
    bar_s = "▓" * bar_w + "░" * (20 - bar_w)
    flag  = "✅" if t >= 0.7 else "❌"
    print(f"  Run {idx:2d}: [{bar_s}] {t:.4f} {flag}")

print()
if rate < 30:
    verdict = "🎯 目标达成：K2.5 成功率低于 30%，题目难度符合预期"
elif rate < 50:
    verdict = "⚠️  成功率 30–50%，题目有一定难度，可适当加强约束"
else:
    verdict = "⚡ 成功率较高 (>50%)，建议增加约束条件难度"
print(f"  {verdict}")
STATSEOF

echo ""
echo "  详细日志: ${LOG_DIR}/"
echo "  汇总文件: ${RESULTS_FILE}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
