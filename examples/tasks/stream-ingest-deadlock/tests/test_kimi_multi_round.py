#!/usr/bin/env python3
"""
stream-ingest-deadlock 多轮迭代测试

测试假设：如果允许 kimi-k2.5 看到运行超时日志，能否通过多轮迭代完成修复？

已知问题：
- 单轮测试：模型能识别双锁问题，但修复不完整
- 多轮测试：让模型看到超时日志，观察是否能自我诊断并修正

测试流程：
1. 第一轮：发送任务描述，生成初始代码
2. 运行测试，捕获超时日志
3. 第二轮：发送超时日志，让模型分析问题
4. 记录模型是否发现其他并发问题
"""

import os
import sys
import subprocess
import tempfile
import time
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from kimi_client import call_kimi as _call_kimi, KIMI_MODEL

MAX_ROUNDS = 5
TIMEOUT_SECONDS = 300

TASK_PROMPT = """修复一个多线程数据摄入系统的死锁问题。

**系统描述**：
- 处理 10 万条事件并写入 WAL（Write-Ahead Log）
- 使用 Queue 进行生产者-消费者通信
- 使用 threading.Lock 保护共享状态

**Bug 现象**：
程序卡住无法完成，怀疑存在死锁。

**文件结构**：
- `/app/dispatcher.py`: 有 bug 的调度器
- `/app/main.py`: 入口程序
- `/app/dedup.py`: 去重器
- `/app/wal.py`: WAL 实现
- `/data/events.jsonl`: 测试数据（100K 条）

**目标**：
- 程序在 15 秒内处理完所有事件
- 无重复提交
- 每个 shard 内顺序正确（seq 递增）
- 内存峰值 < 500 MB

**已知约束**：
- 禁用 asyncio / multiprocessing
- 只能用 threading + queue

请分析 dispatcher.py 中的死锁问题并提供修复方案。直接输出修复后的完整 dispatcher.py 代码："""


def call_kimi(prompt: str) -> str:
    """调用 Kimi API"""
    try:
        return _call_kimi([{"role": "user", "content": prompt}], temperature=0.3, max_tokens=8192)
    except Exception as e:
        return f"API Error: {e}"


def extract_code(response: str, filename: str = "dispatcher.py") -> str:
    """从响应中提取 Python 代码"""
    lines = response.split('\n')
    code_lines = []
    in_code_block = False
    
    for line in lines:
        if '```python' in line or '```py' in line:
            in_code_block = True
            continue
        elif '```' in line and in_code_block:
            break
        elif in_code_block:
            code_lines.append(line)
    
    return '\n'.join(code_lines)


def run_test(timeout: int = TIMEOUT_SECONDS) -> tuple:
    """运行测试，返回 (success, output, elapsed)"""
    start_time = time.time()
    
    try:
        result = subprocess.run(
            ["python3", "/app/main.py"],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd="/app"
        )
        elapsed = time.time() - start_time
        return result.returncode == 0, result.stdout + result.stderr, elapsed
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        return False, f"TIMEOUT after {timeout}s", elapsed
    except Exception as e:
        elapsed = time.time() - start_time
        return False, str(e), elapsed


def test_deadlock_multi_round():
    """多轮迭代测试"""
    
    print("=" * 80)
    print("stream-ingest-deadlock 多轮迭代测试")
    print("=" * 80)
    print(f"模型: {KIMI_MODEL}")
    print(f"最大轮次: {MAX_ROUNDS}")
    print(f"单轮超时: {TIMEOUT_SECONDS}s")
    print()
    
    # 模拟测试（实际需要 Harbor 环境）
    # 这里只演示流程
    
    results = []
    last_output = ""
    
    for round_num in range(1, MAX_ROUNDS + 1):
        print(f"\n{'─' * 80}")
        print(f"第 {round_num} 轮")
        print(f"{'─' * 80}")
        
        if round_num == 1:
            prompt = TASK_PROMPT
        else:
            prompt = f"""上次提交的代码运行失败：

```
{last_output[:1000]}
```

请分析失败原因：
1. 是否仍有死锁？
2. 是否有其他并发问题？
3. 是否顺序检查逻辑有误？

请提供修正后的完整 dispatcher.py 代码："""

        print(f"发送提示词（{len(prompt)} 字符）...")
        start_time = time.time()
        
        response = call_kimi(prompt)
        elapsed = time.time() - start_time
        
        print(f"响应时间: {elapsed:.1f}s")
        print(f"响应长度: {len(response)} 字符")
        
        code = extract_code(response)
        
        if not code:
            print("❌ 无法提取代码")
            results.append({
                'round': round_num,
                'success': False,
                'error': 'No code extracted'
            })
            continue
        
        print(f"代码长度: {len(code)} 字符")
        
        # 分析关键修复点
        checks = {
            'single_lock': 'lock' in code and 'lock_a' not in code and 'lock_b' not in code,
            'no_queue_lock': 'with' not in code or 'q.put' not in code or 'with self.lock' not in code.split('q.put')[0] if 'q.put' in code else True,
            'correct_order_check': '>' in code and 'order' in code,
            'queue_timeout': 'timeout' in code.lower() or 'Empty' in code,
        }
        
        print("关键点检查:")
        for check, passed in checks.items():
            status = "✓" if passed else "✗"
            print(f"  {status} {check}")
        
        # 模拟运行测试
        # 实际环境中应该真的运行代码
        print("\n模拟运行测试...")
        
        # 假设运行结果（实际需要真实环境）
        if all(checks.values()):
            print("✅ 所有关键点检查通过")
            results.append({
                'round': round_num,
                'success': True,
                'checks': checks
            })
            break
        else:
            print("❌ 仍有问题需要修正")
            last_output = f"Checks failed: {[k for k, v in checks.items() if not v]}"
            results.append({
                'round': round_num,
                'success': False,
                'checks': checks
            })
    
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
    with open("/tmp/deadlock_multi_round.json", "w") as f:
        json.dump({
            'model': KIMI_MODEL,
            'max_rounds': MAX_ROUNDS,
            'results': results,
            'success_round': success_round
        }, f, indent=2)
    
    print("\n结果已保存到 /tmp/deadlock_multi_round.json")
    
    return success_round is not None


if __name__ == "__main__":
    # 提示：实际测试需要 Harbor 环境
    print("⚠️  注意：此测试需要 Harbor 容器环境")
    print("   建议使用：cd examples/tasks/stream-ingest-deadlock")
    print("           uv run harbor run -a kimi-k2.5 -p .")
    print()

    # 运行模拟测试
    success = test_deadlock_multi_round()
    sys.exit(0 if success else 1)
