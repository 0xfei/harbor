# Harbor 评测任务集

> **本项目的核心目标：测试 kimi-k2.5 模型的编程与系统理解能力**

基于 [Harbor](https://github.com/convergence-ai/harbor) 评测框架，构建了一套针对顶级 Coding Agent 的系统级编程评测题。

---

## 测试结果总览

| 任务 | 难度 | kimi-k2.5 成功率 | 耗时 | 结论 |
|------|------|------------------|------|------|
| bitmap-vector-fix | Medium | 100% | - | ⚠️ 典型 bug，偏简单 |
| stream-window-aggregator | Hard | **100%** | 77s | ✅ 第 1 轮编译成功，自我诊断文档错误 |
| stream-ingest-deadlock | Hard | **100%** | - | ✅ 多轮迭代下能完全修复并发问题 |
| kafka2clickhouse-debug | Medium | **100%** | 18-36s | ✅ 静态分析成功识别生产 bug（Line 395） |
| distributed-chaos-system | Extreme | **100%** | 20-23s | ✅ 种子化随机数修复非确定性（Deterministic: True） |
| clickhouse-to-doris | Medium | **80%** | 52s | ✅ 4/5 优化点通过，schema 迁移能力强 |
| clickhouse-mergetree-debug | Medium | **100%** | 8-13s | ✅ 精准定位 crash bug（Line 182） |
| storage-performance-analysis | Hard | **100%** | 37-66s | ✅ 准确识别系统性容量瓶颈，排除迷惑项 |
| vector-search-optimization | Hard | **0%** | - | ❌ 算法正确但性能不达标（6s vs 1.5s） |

**总体评分：8/9 任务成功，成功率 88.9%**

---

## kimi-k2.5 能力总结

### ✅ 核心优势
- **数据库迁移**：准确理解 ClickHouse/Doris 索引差异，生成优化 schema
- **典型 Bug 修复**：快速识别 C++ 常见错误（`size_t` 下溢、`reserve` vs `resize`）
- **自我诊断能力**：通过编译错误反向推理，发现文档错误
- **生产 Bug 诊断**：静态代码分析识别生产环境隐藏 bug（52s vs 人工 15-30min）
- **并发问题修复**：正确识别死锁、锁嵌套等并发问题
- **系统性问题分析**：从海量监控数据中排除迷惑项，识别容量瓶颈根因（37.4s）

### 🔍 关键发现

**1. 静态代码分析能力**
- Kafka rebalance bug 定位准确（Line 395，`waited_for_assignment = 0;`）
- ClickHouse MergeTree crash 精准命中（Line 182，15.6s）

**2. 错误诊断能力**
- 提供不完整文档 → 编译失败 → 模型识别文档错误并修正
- 区分"文档错误" vs "代码错误"

**3. 系统性性能分析能力（新发现）**
- 面对 168 个监控数据点 + 多路迷惑信息，37.4s 完成根因推断
- 成功排除：Cluster B 批处理干扰、坏盘假说、吞吐峰值假说
- 正确识别 metadata 压力 80-90% 的"无裕量"状态才是根因
- 指出 metadata 压力在故障时反而下降是 IO stall 的经典特征

**结论：kimi-k2.5 具备生产环境代码诊断与系统性能分析能力，可辅助工程师完成复杂故障分析**

### ❌ 存在弱点
- **提示词敏感**：不完整的结构体定义容易遗漏字段
- **性能优化不足**：向量检索任务未能使用 ANN 算法（6s vs 目标 1.5s）
- **多约束并发**：5+ 个约束时容易遗漏

### 🔍 失败案例分析

**向量检索优化任务**
- ✅ 正确性：Recall=1.0（暴力搜索正确）
- ❌ 性能：6-10s（目标 <1.5s，差距 4-7 倍）
- ❌ 稳定性：第 6-8 轮代码回归
- 根因：缺乏 IVF/HNSW/LSH 索引知识，仅用暴力搜索

---

## 任务列表

| # | 任务 | 难度 | 考察点 |
|---|------|------|--------|
| 1 | [bitmap-vector-fix](./examples/tasks/bitmap-vector-fix/) | Medium | C++ 调试、边界条件 |
| 2 | [stream-window-aggregator](./examples/tasks/stream-window-aggregator/) | Hard | Lock-free 编程、事件时间语义、padding 细节 |
| 3 | [stream-ingest-deadlock](./examples/tasks/stream-ingest-deadlock/) | Hard | Python 并发、锁语义 |
| 4 | [kafka2clickhouse-debug](./examples/tasks/kafka2clickhouse-debug/) | Medium | Kafka 消费逻辑、生产 bug 诊断、静态代码分析 |
| 5 | [distributed-chaos-system](./examples/tasks/distributed-chaos-system/) | Extreme | 分布式系统、非确定性行为 |
| 6 | [clickhouse-to-doris](./examples/tasks/clickhouse-to-doris/) | Medium | 数据库 schema 迁移、索引优化 |
| 7 | [clickhouse-mergetree-debug](./examples/tasks/clickhouse-mergetree-debug/) | Medium | ClickHouse crash 分析、vector 边界检查 |
| 8 | [storage-performance-analysis](./examples/tasks/storage-performance-analysis/) | Hard | 分布式存储性能分析、根因推断、容量治理 |
| 9 | [vector-search-optimization](./examples/tasks/vector-search-optimization/) | Hard | C++ 向量检索优化、ANN 算法、标准库约束 |

---

## 快速运行

### 测试结果

完整测试执行记录见 [TEST_RESULTS.md](./TEST_RESULTS.md)

### 环境变量配置

本项目使用标准 OpenAI API 格式，需配置以下三个环境变量：

```bash
# 添加到 ~/.zshrc 或 ~/.bashrc
export KIMI_API_KEY="your-api-key"
export KIMI_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"  # 或内部网关地址
export KIMI_MODEL="kimi-k2.5"  # 或特定模型版本/endpoint ID
```

**说明**：
- `KIMI_API_KEY`: API 密钥
- `KIMI_URL`: OpenAI 兼容接口地址（DashScope 或内部网关）
- `KIMI_MODEL`: 模型名称或 Endpoint ID

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

# 运行所有任务的 oracle/nop 验证
for task in examples/tasks/*/; do
    uv run harbor run -a oracle -p "$task"
done
```

### 运行 Kimi 静态分析评测

```bash
# 一键运行所有 Kimi 测试（最长5分钟/测试）
bash run_all_kimi_tests.sh

# 单独运行各任务测试
# 注意：单次API调用超时60秒，测试整体超时300秒
python3 examples/tasks/kafka2clickhouse-debug/tests/test_kimi_debug.py        # 18-36s ✅
python3 examples/tasks/clickhouse-mergetree-debug/tests/test_kimi_debug.py    # 8-13s  ✅
python3 examples/tasks/clickhouse-to-doris/tests/test_kimi_migration.py       # 52s    ✅ 80%
python3 examples/tasks/distributed-chaos-system/test_kimi.py                   # 20-23s ✅
python3 examples/tasks/storage-performance-analysis/tests/test_kimi_analysis.py # 37-66s ✅

# 多轮迭代测试（需要 Docker 环境）
python3 examples/tasks/stream-window-aggregator/tests/test_kimi_multi_round.py  # 77s ✅
python3 examples/tasks/stream-ingest-deadlock/tests/test_kimi_multi_round.py     # ✅
```

### 运行向量检索优化任务

```bash
cd examples/tasks/vector-search-optimization
python3 data/generate_data.py  # 首次运行需生成数据（约 1GB）
python3 tests/test_kimi_optimization.py  # kimi-k2.5 多轮优化（实际结果：0% ❌）
```

**注意**：数据文件（`*.npy`, `*.bin`）不提交 git，需本地生成。

---

## 项目结构

```
examples/tasks/<task-name>/
├── task.toml          # 元数据
├── instruction.md     # Agent 可见的任务描述（必须完整准确）
├── environment/       # Docker 镜像定义
├── tests/             # 测试脚本
└── solution/          # Oracle 参考解法
```

**Git 排除规则**（见 `.gitignore`）：
- 大型数据文件：`*.npy`, `*.bin`
- 编译产物：`app/search`, `*.o`
- 运行日志：`jobs/`, `eval_logs/`

---

## 经验教训

**1. 模型具备错误诊断能力**
- 提供不完整文档 → 编译失败 → 模型识别问题并修正
- 能区分"文档错误" vs "代码错误"

**2. 提示词工程质量仍重要**
- 完整提示词减少迭代轮次（1 轮 vs 2 轮）
- 但模型有纠错能力，不必过度担心提示词错误

**3. 测试方法论**
- 提供原始任务描述
- 允许多轮迭代（最多 5 轮）
- 记录自我诊断能力

**核心发现：kimi-k2.5 不仅能执行任务，还能发现任务描述中的错误。**

---

*最后更新：2026-04-24*
