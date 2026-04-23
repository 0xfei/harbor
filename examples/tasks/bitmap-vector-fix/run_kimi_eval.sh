#!/usr/bin/env bash
# 使用 Bailian API（OpenAI-compatible）对 bitmap-vector-fix 进行静态评测
# 注意：这只是一个文本模式的快速预览，真实评测需要 harbor 容器环境

set -euo pipefail

API_KEY="${BAILIAN_API_KEY:-}"
BASE_URL="${BAILIAN_BASE_URL:-https://dashscope.aliyuncs.com/compatible-mode/v1}"
MODEL="${MODEL:-kimi-k2.5}"
N_RUNS="${N_RUNS:-3}"

if [ -z "$API_KEY" ]; then
    echo "Error: BAILIAN_API_KEY not set"
    exit 1
fi

TASK_DIR="$(dirname "$0")"
INSTRUCTION="$TASK_DIR/instruction.md"

# 读取 instruction
INSTRUCTION_TEXT=$(cat "$INSTRUCTION")

# 构建 prompt（包含题目说明）
PROMPT="You are a C++ debugging assistant. Read the following task and respond with the FIXED version of bitmap_manager.cpp.

IMPORTANT: Output ONLY the complete fixed C++ code, no explanations.

Task:
$INSTRUCTION_TEXT

Respond with the complete fixed bitmap_manager.cpp content."

echo "=== Running $N_RUNS evaluations with $MODEL ==="
echo ""

PASS=0
FAIL=0

for i in $(seq 1 "$N_RUNS"); do
    echo "Run $i/$N_RUNS..."
    
    # 调用 API
    RESPONSE=$(curl -s "$BASE_URL/chat/completions" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d "{
            \"model\": \"$MODEL\",
            \"messages\": [{\"role\": \"user\", \"content\": $(jq -Rs . <<< "$PROMPT")}],
            \"temperature\": 0.7,
            \"max_tokens\": 4096
        }")
    
    # 提取代码
    CODE=$(echo "$RESPONSE" | jq -r '.choices[0].message.content // empty' 2>/dev/null)
    
    if [ -z "$CODE" ]; then
        echo "  API error or empty response"
        FAIL=$((FAIL + 1))
        continue
    fi
    
    # 保存代码
    TEMP_DIR=$(mktemp -d)
    echo "$CODE" > "$TEMP_DIR/bitmap_manager.cpp"
    
    # 复制头文件和测试
    cp "$TASK_DIR/solution/bitmap.h" "$TEMP_DIR/"
    cp "$TASK_DIR/solution/hash.h" "$TEMP_DIR/"
    cp "$TASK_DIR/solution/bitmap_manager.h" "$TEMP_DIR/"
    cp "$TASK_DIR/solution/bitmap_manager_test.cpp" "$TEMP_DIR/"
    
    # 尝试编译
    if g++ -std=c++11 -o "$TEMP_DIR/test" "$TEMP_DIR/bitmap_manager_test.cpp" "$TEMP_DIR/bitmap_manager.cpp" 2>/dev/null; then
        # 运行测试
        OUTPUT=$("$TEMP_DIR/test" 2>&1 || true)
        PASS_COUNT=$(echo "$OUTPUT" | grep -c '^\s*\[PASS\]' || echo 0)
        FAIL_COUNT=$(echo "$OUTPUT" | grep -c '^\s*\[FAIL\]' || echo 0)
        
        echo "  PASS=$PASS_COUNT FAIL=$FAIL_COUNT"
        
        if [ "$FAIL_COUNT" -eq 0 ] && [ "$PASS_COUNT" -gt 0 ]; then
            PASS=$((PASS + 1))
        else
            FAIL=$((FAIL + 1))
        fi
    else
        echo "  Compilation failed"
        FAIL=$((FAIL + 1))
    fi
    
    rm -rf "$TEMP_DIR"
done

echo ""
echo "=== Results ==="
echo "PASS: $PASS / $N_RUNS"
echo "FAIL: $FAIL / $N_RUNS"
echo "Success rate: $(python3 -c "print(round($PASS / $N_RUNS * 100, 1))")%"
