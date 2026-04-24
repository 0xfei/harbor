#!/usr/bin/env python3
"""
测试 harbor-self-optimization 任务
验证 kimi-k2.5 能否正确完成本项目自优化
"""

import os
import sys
import subprocess
import time
from pathlib import Path

# 环境变量验证
KIMI_API_KEY = os.environ.get("KIMI_API_KEY", "")
KIMI_URL = os.environ.get("KIMI_URL", "")
KIMI_MODEL = os.environ.get("KIMI_MODEL", "")


def test_env_vars():
    """测试环境变量是否正确设置（严格遵守要求1）"""
    assert KIMI_API_KEY, "KIMI_API_KEY 未设置"
    assert KIMI_URL, "KIMI_URL 未设置"
    assert KIMI_MODEL, "KIMI_MODEL 未设置"
    print("✓ 环境变量检查通过")


def test_no_hardcoded_vars():
    """测试脚本是否硬编码了环境变量（严格遵守要求3）"""
    solve_sh = Path("examples/tasks/harbor-self-optimization/solution/solve.sh")
    content = solve_sh.read_text()
    
    # 不应该有硬编码的 API key
    assert "sk-" not in content, "发现硬编码的 API key"
    assert "export KIMI_API_KEY=" not in content, "不应该 export KIMI_API_KEY"
    assert "export KIMI_URL=" not in content, "不应该 export KIMI_URL"
    assert "export KIMI_MODEL=" not in content, "不应该 export KIMI_MODEL"
    
    # 应该使用 :? 验证
    assert ': "${KIMI_API_KEY:?KIMI_API_KEY 未设置}"' in content or ': "${KIMI_API_KEY:?}' in content, \
        "应该使用 :? 验证环境变量"
    
    print("✓ 环境变量使用检查通过")


def test_circular_dependency_detection():
    """测试是否识别了循环依赖"""
    solve_sh = Path("examples/tasks/harbor-self-optimization/solution/solve.sh")
    content = solve_sh.read_text()
    
    # 应该有循环依赖识别的代码
    assert "循环依赖" in content or "circular" in content.lower() or "meta-evaluation" in content, \
        "脚本应该识别循环依赖问题"
    
    print("✓ 循环依赖识别检查通过")


def test_execution_logging():
    """测试是否有执行记录功能"""
    solve_sh = Path("examples/tasks/harbor-self-optimization/solution/solve.sh")
    content = solve_sh.read_text()
    
    # 应该有记录时间、结果的代码
    assert "start" in content.lower() and "end" in content.lower(), \
        "应该记录开始和结束时间"
    assert "elapsed" in content.lower() or "耗时" in content, \
        "应该记录耗时"
    assert "PASS" in content and "FAIL" in content, \
        "应该记录测试结果"
    assert ".jsonl" in content or ".log" in content or ".json" in content, \
        "应该输出日志文件"
    
    print("✓ 执行记录功能检查通过")


def test_timeout_handling():
    """测试超时处理"""
    solve_sh = Path("examples/tasks/harbor-self-optimization/solution/solve.sh")
    content = solve_sh.read_text()
    
    # 应该有超时相关的代码
    assert "timeout" in content.lower() or "超时" in content, \
        "应该处理超时问题"
    
    # 应该有根据 API 响应调整超时的逻辑
    assert "API" in content and ("响应" in content or "response" in content.lower()), \
        "应该根据 API 响应调整超时"
    
    print("✓ 超时处理检查通过")


def test_docker_support():
    """测试 Docker 支持"""
    solve_sh = Path("examples/tasks/harbor-self-optimization/solution/solve.sh")
    content = solve_sh.read_text()
    
    # 应该有 Docker 相关的代码
    assert "docker" in content.lower(), "应该支持 Docker 测试"
    assert "oracle" in content.lower(), "应该运行 Oracle 测试"
    assert "nop" in content.lower(), "应该运行 Nop 测试"
    
    print("✓ Docker 支持检查通过")


def test_git_branch_management():
    """测试是否正确使用 Git 分支管理（严格要求1）"""
    solve_sh = Path("examples/tasks/harbor-self-optimization/solution/solve.sh")
    content = solve_sh.read_text()
    
    # 必须包含创建分支的代码
    assert "git checkout -b" in content or "git switch -c" in content, \
        "必须先创建新分支进行改动"
    
    # 不应该直接在 main 上提交
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'git checkout' in line and 'main' in line:
            # 如果检出 main，前面必须先创建过分支
            context = '\n'.join(lines[max(0, i-5):i+5])
            assert 'git checkout -b' in context or 'git switch -c' in context, \
                "不能直接检出 main 分支进行修改"
    
    print("✓ Git 分支管理检查通过")


def test_docker_isolation():
    """测试是否在 Docker 容器中隔离执行（严格要求2）"""
    solve_sh = Path("examples/tasks/harbor-self-optimization/solution/solve.sh")
    content = solve_sh.read_text()
    
    # 必须使用 Docker 运行
    assert "docker run" in content or "docker exec" in content, \
        "必须在 Docker 容器中执行改动"
    
    # 必须包含代码克隆
    assert "git clone" in content, \
        "必须在容器中克隆代码仓库"
    
    # 不能使用相对路径（如 .. 或 .）
    assert "../" not in content and "./workspace" not in content, \
        "必须使用绝对路径，不能使用相对路径"
    
    # 应该有工作目录设置
    assert "WORKDIR" in content or "/workspace" in content or "/tmp/harbor" in content, \
        "应该设置明确的工作目录"
    
    print("✓ Docker 隔离环境检查通过")


def test_iteration_convergence():
    """测试多轮迭代和收敛"""
    solve_sh = Path("examples/tasks/harbor-self-optimization/solution/solve.sh")
    content = solve_sh.read_text()
    
    # 应该有迭代相关的代码
    assert "round" in content.lower() or "迭代" in content or "iterate" in content.lower(), \
        "应该支持多轮迭代"
    
    # 应该有收敛判断
    assert "converge" in content.lower() or "收敛" in content, \
        "应该判断是否收敛"
    
    print("✓ 迭代收敛检查通过")


def test_readme_update():
    """测试 README.md 更新功能"""
    solve_sh = Path("examples/tasks/harbor-self-optimization/solution/solve.sh")
    content = solve_sh.read_text()
    
    # 应该有更新 README 的代码
    assert "README" in content, "应该更新 README.md"
    assert "分数" in content or "score" in content.lower(), \
        "应该记录分数"
    
    print("✓ README 更新检查通过")


def test_actual_execution():
    """实际执行脚本（可选，需要真实 API）"""
    if not all([KIMI_API_KEY, KIMI_URL, KIMI_MODEL]):
        print("⊘ 跳过实际执行（环境变量未设置）")
        return
    
    print("执行 solve.sh...")
    start = time.time()
    
    result = subprocess.run(
        ["bash", "examples/tasks/harbor-self-optimization/solution/solve.sh"],
        capture_output=True,
        text=True,
        timeout=600  # 10分钟总超时
    )
    
    elapsed = time.time() - start
    print(f"执行耗时: {elapsed:.1f}s")
    print(f"退出码: {result.returncode}")
    
    if result.returncode != 0:
        print("错误输出:", result.stderr[:500])
    
    # 检查是否生成了日志文件
    log_files = list(Path(".").glob("optimization_log_*.jsonl"))
    assert log_files, "应该生成日志文件"
    
    print("✓ 实际执行检查通过")


def main():
    print("=" * 80)
    print("Harbor 项目自优化任务测试")
    print("=" * 80)
    print()
    
    tests = [
        ("环境变量验证", test_env_vars),
        ("无硬编码变量", test_no_hardcoded_vars),
        ("循环依赖识别", test_circular_dependency_detection),
        ("执行记录功能", test_execution_logging),
        ("超时处理", test_timeout_handling),
        ("Git 分支管理", test_git_branch_management),
        ("Docker 隔离环境", test_docker_isolation),
        ("Docker 支持", test_docker_support),
        ("迭代收敛", test_iteration_convergence),
        ("README 更新", test_readme_update),
        ("实际执行", test_actual_execution),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        print(f"\n--- {name} ---")
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"❌ 失败: {e}")
            failed += 1
        except Exception as e:
            print(f"⚠ 错误: {e}")
            failed += 1
    
    print()
    print("=" * 80)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 80)
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
