#!/usr/bin/env python3
"""
stream-window-aggregator 多轮迭代测试

测试假设：如果允许 kimi-k2.5 看到编译错误日志后自我修正，能否通过？

测试流程：
1. 第一轮：发送任务描述，生成初始代码
2. 尝试编译，捕获错误日志
3. 第二轮：发送错误日志，让模型修正
4. 最多迭代 5 轮，统计最终通过率
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

# 任务描述
TASK_PROMPT = """实现一个 C++ 程序 `/app/aggregator`，计算每位用户在 30 秒事件时间滑动窗口内的 Top-3 兴趣类目。

**输入格式**（`/data/events.bin`，little-endian 二进制）：
```c
struct Event {
    uint64_t event_ts_ms;   // 事件时间戳（毫秒）
    uint32_t user_id;
    uint16_t category_id;   // 视频类目（0–999）
    uint16_t watch_seconds; // 观看时长（1–600 秒）
    uint8_t  _pad[8];       // 填充至 24 字节
};
static_assert(sizeof(Event) == 24, "Event must be 24 bytes");
```

**输出格式**（`/data/output.tsv`）：
```
<user_id>\t<cat1>:<score1>,<cat2>:<score2>,<cat3>:<score3>
```
按 user_id 数值升序排列。

**约束（必须全部满足）**：
1. **禁锁**：不得使用 mutex/semaphore/rwlock，只能用 std::atomic
2. **禁关联容器**：不得使用 std::map/unordered_map/set 系列
3. **内存限制**：峰值 RSS < 200 MB
4. **事件时间语义**：窗口以用户的 max event_ts 为锚点，必须两遍扫描（第一遍找 max_ts，第二遍聚合）
5. **精确 4 线程**：必须创建 4 个 worker 线程处理数据
6. **无第三方库**：只能用 C++17 标准库 + POSIX API

请直接输出完整的 C++ 代码："""


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
    # 查找 ```cpp 或 ```c++ 代码块
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
    """尝试编译代码，返回 (success, error_log)"""
    with tempfile.TemporaryDirectory() as tmpdir:
        src_file = Path(tmpdir) / "aggregator.cpp"
        out_file = Path(tmpdir) / "aggregator"
        
        src_file.write_text(code)
        
        # 尝试编译
        result = subprocess.run(
            ["g++", "-std=c++17", "-O2", "-pthread", "-o", str(out_file), str(src_file)],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            return True, ""
        else:
            error_log = result.stderr
            return False, error_log


def test_multi_round():
    """多轮迭代测试"""
    print("=" * 80)
    print("stream-window-aggregator 多轮迭代测试")
    print("=" * 80)
    print(f"模型: {MODEL}")
    print(f"最大轮次: {MAX_ROUNDS}")
    print()
    
    results = []
    
    for round_num in range(1, MAX_ROUNDS + 1):
        print(f"\n{'─' * 80}")
        print(f"第 {round_num} 轮")
        print(f"{'─' * 80}")
        
        if round_num == 1:
            # 第一轮：发送任务描述
            prompt = TASK_PROMPT
        else:
            # 后续轮：发送错误日志
            prompt = f"""上次提交的代码编译失败，错误日志如下：

```
{last_error}
```

请分析错误原因，修正代码后重新提交完整的 C++ 程序。

**注意**：
- Event struct 必须包含 `_pad[8]` 字段使 sizeof(Event) == 24
- 确保 static_assert 不触发
- 检查所有约束是否满足"""

        print(f"发送提示词（{len(prompt)} 字符）...")
        start_time = time.time()
        
        response = call_kimi(prompt)
        elapsed = time.time() - start_time
        
        print(f"响应时间: {elapsed:.1f}s")
        print(f"响应长度: {len(response)} 字符")
        
        # 提取代码
        code = extract_code(response)
        
        if not code:
            print("❌ 无法提取代码")
            results.append({
                'round': round_num,
                'success': False,
                'error': 'No code extracted'
            })
            last_error = "无法从响应中提取有效的 C++ 代码"
            continue
        
        print(f"代码长度: {len(code)} 字符")
        
        # 检查关键点
        checks = {
            'has_pad': '_pad[8]' in code or '_pad[8]' in code.replace(' ', ''),
            'has_static_assert': 'static_assert' in code,
            'has_atomic': 'atomic' in code,
            'has_thread': 'thread' in code or 'pthread' in code,
        }
        
        print("关键点检查:")
        for check, passed in checks.items():
            status = "✓" if passed else "✗"
            print(f"  {status} {check}")
        
        # 尝试编译
        print("尝试编译...")
        success, error_log = compile_code(code)
        
        if success:
            print("✅ 编译成功！")
            results.append({
                'round': round_num,
                'success': True,
                'checks': checks
            })
            break
        else:
            print("❌ 编译失败")
            print("错误日志:")
            print(error_log[:500])
            results.append({
                'round': round_num,
                'success': False,
                'error': error_log[:500],
                'checks': checks
            })
            last_error = error_log
    
    # 输出总结
    print("\n" + "=" * 80)
    print("测试总结")
    print("=" * 80)
    
    success_round = None
    for r in results:
        if r['success']:
            success_round = r['round']
            break
    
    if success_round:
        print(f"✅ 在第 {success_round} 轮成功通过")
    else:
        print(f"❌ {MAX_ROUNDS} 轮迭代后仍未通过")
    
    print(f"\n各轮结果:")
    for r in results:
        status = "✅" if r['success'] else "❌"
        print(f"  第 {r['round']} 轮: {status}")
        if 'checks' in r:
            passed = sum(r['checks'].values())
            total = len(r['checks'])
            print(f"    关键点: {passed}/{total}")
    
    # 保存结果
    with open("/tmp/stream_window_multi_round.json", "w") as f:
        json.dump({
            'model': MODEL,
            'max_rounds': MAX_ROUNDS,
            'results': results,
            'success_round': success_round
        }, f, indent=2)
    
    print("\n结果已保存到 /tmp/stream_window_multi_round.json")
    
    return success_round is not None


if __name__ == "__main__":
    if not API_KEY:
        print("Error: BAILIAN_API_KEY not set")
        sys.exit(1)
    
    success = test_multi_round()
    sys.exit(0 if success else 1)
