#!/usr/bin/env python3
"""
stream-window-aggregator 真实场景测试

测试假设：提供有错误的文档（instruction.md），看模型能否通过分析编译错误
发现隐藏问题，而不是直接告诉它问题所在。

这更符合现实场景：文档可能存在错误，工程师需要通过错误日志反向推理。

测试流程：
1. 提供原始的（不完整的）instruction.md 作为任务描述
2. 第一轮：模型生成初始代码
3. 尝试编译，捕获错误日志
4. 第二轮：仅提供错误日志，看模型能否自我诊断
5. 记录模型是否能发现"文档错误" vs "代码错误"
"""

import os
import sys
import subprocess
import tempfile
import requests
import json
import time
from pathlib import Path

# 配置
API_KEY = os.environ.get("BAILIAN_API_KEY", "")
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "kimi-k2.5"
MAX_ROUNDS = 5

# 原始的（有问题的）instruction.md 内容
ORIGINAL_INSTRUCTION = """# Stream Window Aggregator

## Background

You are working on a **real-time video recommendation pipeline**. The pipeline
ingests a stream of user click events and must continuously maintain, for each
user, the **top-3 most-watched video categories** within a **30-second sliding
window based on event timestamps** (not wall-clock time).

## Your Task

Implement a C++ program `/app/aggregator` that:

1. Reads a **binary event log** from `/data/events.bin` (format described below).
2. Processes events in **4 parallel worker threads** (exactly 4, not more, not fewer).
3. Produces an output file `/data/output.tsv` with the aggregated results.

### Input Format: `/data/events.bin`

The file is a sequence of fixed-size records, **little-endian**:

```
struct Event {
    uint64_t event_ts_ms;   // event timestamp in milliseconds (event time)
    uint32_t user_id;       // user identifier
    uint16_t category_id;   // video category (0–999)
    uint16_t watch_seconds; // how long the user watched (1–600)
};
```

The file contains **500,000 events**. Events are **NOT** sorted by timestamp.

### Output Format: `/data/output.tsv`

For each `user_id` that appears in the input, write exactly one line:

```
<user_id>\t<cat1>:<score1>,<cat2>:<score2>,<cat3>:<score3>
```

Lines must be sorted in **ascending numeric order of `user_id`**.

### Mandatory Constraints

- **No mutex/lock**: Use only atomic operations
- **No map/set**: Use only array-based structures
- **Memory limit**: Peak RSS < 200 MB
- **Event time semantics**: Window anchored at max_ts per user
- **Exactly 4 worker threads**
- **C++17 only**, no third-party libraries

### Compilation

```bash
g++ -O2 -std=c++17 -pthread -o /app/aggregator /app/aggregator.cpp
```"""


def call_kimi(prompt: str) -> str:
    """调用 kimi-k2.5 API"""
    try:
        response = requests.post(
            f"{BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 8192
            },
            timeout=180
        )
        
        content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        return content
    except Exception as e:
        return f"API Error: {e}"


def extract_code(response: str) -> str:
    """从响应中提取 C++ 代码"""
    lines = response.split('\n')
    code_lines = []
    in_code_block = False
    
    for line in lines:
        if '```cpp' in line or '```c++' in line or '```c' in line.lower():
            in_code_block = True
            continue
        elif '```' in line and in_code_block:
            break
        elif in_code_block:
            code_lines.append(line)
    
    return '\n'.join(code_lines)


def compile_code(code: str) -> tuple:
    """尝试编译代码"""
    with tempfile.TemporaryDirectory() as tmpdir:
        src_file = Path(tmpdir) / "aggregator.cpp"
        out_file = Path(tmpdir) / "aggregator"
        
        src_file.write_text(code)
        
        result = subprocess.run(
            ["g++", "-std=c++17", "-O2", "-pthread", "-o", str(out_file), str(src_file)],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            return True, "", code
        else:
            return False, result.stderr, code


def test_realistic_scenario():
    """真实场景测试：提供错误文档，看模型能否自我诊断"""
    
    print("=" * 80)
    print("stream-window-aggregator 真实场景测试")
    print("=" * 80)
    print("测试场景：文档可能有错误，模型需要通过编译错误自我诊断")
    print()
    
    # 第一轮：提供原始文档
    print("=" * 80)
    print("第 1 轮：提供原始文档（可能不完整）")
    print("=" * 80)
    
    prompt_round1 = f"""{ORIGINAL_INSTRUCTION}

Please implement the complete C++ program. Pay close attention to the binary file format specification."""

    print(f"发送任务描述（{len(prompt_round1)} 字符）...")
    start_time = time.time()
    
    response = call_kimi(prompt_round1)
    elapsed = time.time() - start_time
    
    print(f"响应时间: {elapsed:.1f}s")
    
    code = extract_code(response)
    
    # 检查代码是否包含 static_assert
    has_static_assert = 'static_assert' in code
    has_pad_field = '_pad' in code or 'padding' in code.lower()
    
    print(f"\n生成代码分析:")
    print(f"  代码长度: {len(code)} 字符")
    print(f"  包含 static_assert: {has_static_assert}")
    print(f"  包含 padding 字段: {has_pad_field}")
    
    # 尝试编译
    print("\n尝试编译...")
    success, error_log, code = compile_code(code)
    
    if success:
        print("✅ 编译成功！")
        
        # 检查运行结果
        print("\n检查运行时行为...")
        # 这里可以添加更多运行时检查
        
        return {
            'success_round': 1,
            'total_rounds': 1,
            'discovery_type': 'direct',
            'final_success': True
        }
    
    print("❌ 编译失败")
    print(f"\n错误日志:")
    print("-" * 80)
    print(error_log[:1000])
    print("-" * 80)
    
    # 第二轮：仅提供错误日志，看模型能否诊断
    print("\n" + "=" * 80)
    print("第 2 轮：提供编译错误，让模型自我诊断")
    print("=" * 80)
    
    prompt_round2 = f"""The code you generated failed to compile. Here is the compilation error:

```
{error_log}
```

Please analyze:
1. What is causing this error?
2. Is the issue in your code or in the task specification?
3. What is the actual structure of the binary file based on the error?

Then provide a corrected implementation."""

    print(f"发送错误日志（{len(prompt_round2)} 字符）...")
    start_time = time.time()
    
    response = call_kimi(prompt_round2)
    elapsed = time.time() - start_time
    
    print(f"响应时间: {elapsed:.1f}s")
    
    # 分析模型是否发现了文档问题
    discovery_types = {
        'blamed_code': 'assume error in code' in response.lower() or 'my mistake' in response.lower(),
        'blamed_spec': 'specification' in response.lower() or 'document' in response.lower() or 'task description' in response.lower(),
        'found_size_issue': 'sizeof' in response or '24 bytes' in response or 'size' in response,
        'found_padding': 'pad' in response.lower() or 'padding' in response.lower(),
    }
    
    print(f"\n模型诊断分析:")
    for dtype, found in discovery_types.items():
        status = "✓" if found else "✗"
        print(f"  {status} {dtype}")
    
    code = extract_code(response)
    code_has_pad = '_pad' in code or 'padding' in code.lower()
    code_has_assert = 'static_assert' in code and 'sizeof' in code
    
    print(f"\n修正后的代码:")
    print(f"  包含 padding: {code_has_pad}")
    print(f"  包含 sizeof 检查: {code_has_assert}")
    
    # 再次编译
    print("\n尝试编译修正后的代码...")
    success2, error_log2, code = compile_code(code)
    
    if success2:
        print("✅ 编译成功！模型成功自我诊断")
        
        return {
            'success_round': 2,
            'total_rounds': 2,
            'discovery_type': 'self_diagnosis',
            'found_doc_error': discovery_types['blamed_spec'] or discovery_types['found_size_issue'],
            'added_padding': code_has_pad,
            'final_success': True
        }
    
    print("❌ 仍然编译失败")
    
    # 如果还有时间，继续迭代
    # 这里简化为两轮测试
    
    return {
        'success_round': None,
        'total_rounds': 2,
        'final_success': False,
        'discovery_types': discovery_types
    }


def main():
    if not API_KEY:
        print("Error: BAILIAN_API_KEY not set")
        sys.exit(1)
    
    result = test_realistic_scenario()
    
    # 输出最终结论
    print("\n" + "=" * 80)
    print("测试总结")
    print("=" * 80)
    
    if result['final_success']:
        print(f"✅ 模型在第 {result['success_round']} 轮成功通过")
        
        if result.get('found_doc_error'):
            print("✓ 模型成功识别出文档问题")
        else:
            print("✗ 模型没有明确识别文档错误，但通过试错修复了代码")
    else:
        print("❌ 模型未能通过测试")
        print("这说明：模型可能需要更明确的提示才能发现隐藏问题")
    
    # 保存结果
    with open("/tmp/stream_window_realistic_test.json", "w") as f:
        json.dump(result, f, indent=2)
    
    print("\n结果已保存到 /tmp/stream_window_realistic_test.json")


if __name__ == "__main__":
    main()
