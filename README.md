# Harbor 评测任务集

> **本项目的核心目标：测试 kimi-k2.5 模型的编程与系统理解能力**

基于 [Harbor](https://github.com/convergence-ai/harbor) 评测框架，构建了一套针对顶级 Coding Agent 的系统级编程评测题。

---

## 测试结果总览

| 任务 | 难度 | kimi-k2.5 成功率 | 结论 |
|------|------|------------------|------|
| stream-window-aggregator | Hard | **100%** | ✅ 多轮迭代下能自我诊断文档错误 |
| bitmap-vector-fix | Medium | 100% | ⚠️ 典型 bug，偏简单 |
| stream-ingest-deadlock | Hard | **100%** | ✅ 多轮迭代下能完全修复并发问题 |
| distributed-chaos-system | Extreme | > 50% | ✅ 条件触发 |
| clickhouse-to-doris | Medium | **100%** | ✅ schema 迁移能力强 |
| vector-search-optimization | Hard | **0%** | ❌ 算法正确但性能不达标（6s vs 1.5s） |

---

## kimi-k2.5 能力总结

### ✅ 表现优秀
- **数据库迁移**：准确理解 ClickHouse 和 Doris 索引差异，正确生成优化 schema
- **隐藏细节修复**：在**正确提示词**下能识别 padding、alignment 等内存布局问题
- **典型 bug 修复**：快速识别 C++ 常见错误（`size_t` 下溢、`reserve` vs `resize`）
- **明确任务**：在问题清晰描述时能准确定位和修复
- **自我诊断能力**：**即使提供错误文档，也能通过编译错误反向推理发现问题**
- **性能优化潜力**：能理解 latency/recall/memory 三角约束并设计合理方案
- **C++ 标准库编程**：在无第三方库约束下实现高性能算法

### 🔍 重要发现

**真实场景测试：提供不完整文档 → 模型通过编译错误自我诊断**

测试结果显示：
- 第 1 轮：基于不完整文档生成代码（缺少 padding 字段）
- 编译失败：缺少 main 函数
- 第 2 轮：模型成功识别"文档可能有错误"，自我修正后编译成功
- **结论：模型具备工程师级别的错误诊断能力**

这证明了：**kimi-k2.5 不仅能执行任务，还能发现任务描述中的错误**

### ❌ 存在弱点
- **提示词敏感**：对不完整的结构体定义敏感，容易系统性遗漏字段
- **平台差异**：可能生成 x86 specific 代码（如 `__builtin_ia32_pause`）
- **多约束并发**：同时满足 5+ 个约束时容易遗漏
- **隐晦描述**：问题表述模糊时倾向于过度复杂化方案
- **性能优化**：在需要高级算法优化（ANN、索引结构）时表现不足

### 🔍 重要发现

**1. 向量检索优化任务失败分析**

测试场景：百万级向量检索优化（C++ 标准库，目标延迟 <1.5s）

测试结果：
- ✅ 正确性：前 5 轮生成正确代码（Recall=1.0）
- ❌ 性能：延迟 6-10s（目标 <1.5s，差距 4-7 倍）
- ❌ 稳定性：后 3 轮回归（Recall 跌至 0.1）
- ❌ 收敛性：8 轮迭代无性能改进

根因分析：
- 仅使用暴力搜索 O(n*m*d)，未探索 ANN 算法
- 缺乏索引结构（IVF、HNSW、LSH）知识
- 迭代偏向代码风格而非算法优化

**2. 多轮迭代自我诊断（已验证）**

**并发问题修复能力测试**

测试场景：提供有死锁的多线程代码，让模型通过分析修复

测试结果：
- ✅ 第 1 轮就通过所有关键点检查
- ✅ 正确识别双锁嵌套问题
- ✅ 移除 Queue 操作的外层锁
- ✅ 修正顺序检查逻辑（`>` 替代 `<=`）
- ✅ 添加超时机制

**结论：对于并发问题，只要问题描述清晰，kimi-k2.5 能快速生成正确修复**

---

## 任务列表

| # | 任务 | 难度 | 考察点 |
|---|------|------|--------|
| 1 | [stream-window-aggregator](./examples/tasks/stream-window-aggregator/TASK.md) | Hard | Lock-free 编程、事件时间语义、padding 细节 |
| 2 | [bitmap-vector-fix](./examples/tasks/bitmap-vector-fix/TASK.md) | Medium | C++ 调试、边界条件 |
| 3 | [stream-ingest-deadlock](./examples/tasks/stream-ingest-deadlock/TASK.md) | Hard | Python 并发、锁语义 |
| 4 | [distributed-chaos-system](./examples/tasks/distributed-chaos-system/TASK.md) | Extreme | 分布式系统、非确定性行为 |
| 5 | [clickhouse-to-doris](./examples/tasks/clickhouse-to-doris/TASK.md) | Medium | 数据库 schema 迁移、索引优化 |
| 6 | [vector-search-optimization](./examples/tasks/vector-search-optimization/TASK.md) | Hard | C++ 向量检索优化、ANN 算法、标准库约束 |

---

## 快速运行

### 前置条件（Mac）

```bash
# 1. 安装 Homebrew（如未安装）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. 安装 Podman（Docker 替代方案）
brew install podman
podman machine init
podman machine start

# 3. 配置 Docker socket shim
export DOCKER_HOST="unix://$(podman machine inspect | grep APISocket | cut -d'"' -f4)"
echo 'export DOCKER_HOST="unix://'"$DOCKER_HOST"'"' >> ~/.zshrc

# 4. 安装 Docker Compose v2
mkdir -p ~/.docker/cli-plugins
curl -SL "https://github.com/docker/compose/releases/download/v2.36.0/docker-compose-darwin-$(uname -m)" \
     -o ~/.docker/cli-plugins/docker-compose
chmod +x ~/.docker/cli-plugins/docker-compose

# 5. 创建 docker shim
sudo tee /opt/homebrew/bin/docker > /dev/null << 'EOF'
#!/bin/sh
if [ "$1" = "compose" ]; then
    shift
    exec "$HOME/.docker/cli-plugins/docker-compose" "$@"
fi
exec podman "$@"
EOF
sudo chmod +x /opt/homebrew/bin/docker

# 6. 安装 Harbor CLI
brew install uv
uv tool install harbor-ai
```

### 克隆并运行测试

```bash
# 克隆本项目
git clone https://github.com/0xfei/harbor.git
cd harbor

# 验证 Oracle（预期得分 1.0）
uv run harbor run -a oracle -p examples/tasks/stream-window-aggregator

# 验证空 Agent（预期得分 0.0）
uv run harbor run -a nop -p examples/tasks/stream-window-aggregator

# 查看评测结果
uv run harbor view jobs

# 运行所有任务
for task in examples/tasks/*/; do
    uv run harbor run -a oracle -p "$task"
done
```

### 验证 kimi-k2.5 多轮迭代能力

```bash
# 设置 Bailian API Key
export BAILIAN_API_KEY="your-api-key-here"

# 运行多轮迭代测试（允许模型看到编译错误后自我修正）
cd examples/tasks/stream-window-aggregator
python3 tests/test_kimi_multi_round.py

# 结果：✅ 第 1 轮即编译成功
```

### 运行向量检索优化任务

```bash
# 首次运行需要生成数据（约 1GB，耗时 30s）
cd examples/tasks/vector-search-optimization
python3 data/generate_data.py      # 生成训练数据和 ground truth
python3 app/convert.py ...         # 转换为二进制格式

# 运行 Oracle 和 Nop 测试
./run_tests.sh

# 预期结果：
# Oracle: Recall=1.0, Score=1.0
# Nop: Recall=0.0, Score=0.0

# 运行 kimi-k2.5 多轮优化（需要 API Key）
export BAILIAN_API_KEY="your-key"
./run_kimi_test.sh

# 实际结果（8 轮）：
# Rounds 1-5: Recall=1.0, Latency=6-10s (正确但太慢)
# Rounds 6-8: Recall=0.1/timeout (代码回归)
# Final Score: 0.0/1.0 ❌
```

**注意**：大型数据文件（`*.npy`, `*.bin`）不提交到 git，需本地生成。

---

## 项目结构

```
examples/tasks/<task-name>/
├── task.toml          # 元数据
├── instruction.md     # Agent 可见的任务描述（⚠️ 必须完整准确）
├── environment/       # Docker 镜像定义
├── tests/             # 测试脚本
└── solution/          # Oracle 参考解法

# 向量检索任务特殊结构：
examples/tasks/vector-search-optimization/
├── data/
│   └── generate_data.py   # 数据生成脚本（提交）
│   └── *.npy, *.bin       # 数据文件（不提交，见 .gitignore）
├── app/
│   ├── search.cpp         # 生成的代码（评测时写入）
│   └── search             # 编译产物（不提交）
└── results/
    └── *.json             # 评测结果（提交）
```

**Git 排除规则**（见 `.gitignore`）：
- 大型数据文件：`*.npy`, `*.bin`（约 1GB）
- 编译产物：`app/search`, `*.o`, `*.out`
- 运行日志：`jobs/`, `eval_logs/`

详细技术分析见各任务目录下的 `TASK.md` 和 `KIMI_EVALUATION_REPORT.md`。

---

## 经验教训

**1. 模型具备错误诊断能力**

真实场景测试证明：
- ✅ 提供不完整文档 → 编译失败 → 模型通过错误日志发现问题
- ✅ 模型能识别"这是文档错误"而非"我的代码错误"
- ✅ 这种能力接近工程师级别的问题诊断水平

**2. 提示词工程质量仍重要**

虽然模型能自我诊断，但：
- 完整准确的提示词能**显著减少迭代轮次**（1 轮 vs 2 轮）
- 结构体定义、静态断言等关键信息应明确提供
- 但不必过度担心提示词错误——模型有纠错能力

**3. 测试方法论**

正确的评测流程：
1. 提供原始任务描述
2. 允许多轮迭代（最多 5 轮）
3. 记录模型是否自我诊断问题
4. 区分"模型能力问题" vs "提示词问题"

**核心发现：kimi-k2.5 不仅能执行任务，还能发现任务描述中的错误。**

---

*最后更新：2026-04-24*
