# Harbor 评测任务集

> **本项目的核心目标：测试 kimi-k2.5 模型的编程与系统理解能力**

基于 [Harbor](https://github.com/convergence-ai/harbor) 评测框架，构建了一套针对顶级 Coding Agent 的系统级编程评测题。

---

## 测试结果总览

| 任务 | 难度 | kimi-k2.5 成功率 | 结论 |
|------|------|------------------|------|
| stream-window-aggregator | Hard | 0% | ✅ 有效卡住 - 隐藏细节陷阱 |
| bitmap-vector-fix | Medium | 100% | ⚠️ 偏简单 - 典型 bug |
| stream-ingest-deadlock | Hard | < 30% | ✅ 有效卡住 - 并发语义复杂 |
| distributed-chaos-system | Extreme | > 50% | ✅ 条件触发 - 依赖问题描述 |
| clickhouse-to-doris | Medium | **100%** | ✅ 完美 - schema 迁移能力强 |

---

## kimi-k2.5 能力总结

### ✅ 表现优秀
- **数据库迁移**：准确理解 ClickHouse 和 Doris 索引差异，正确生成优化 schema
- **典型 bug 修复**：快速识别 C++ 常见错误（`size_t` 下溢、`reserve` vs `resize`）
- **明确任务**：在问题清晰描述时能准确定位和修复

### ❌ 存在弱点
- **隐藏细节**：对 padding、alignment 等内存布局问题敏感度不足
- **平台差异**：可能生成 x86 specific 代码（如 `__builtin_ia32_pause`）
- **多约束并发**：同时满足 5+ 个约束时容易遗漏
- **隐晦描述**：问题表述模糊时倾向于过度复杂化方案

---

## 任务列表

| # | 任务 | 难度 | 考察点 |
|---|------|------|--------|
| 1 | [stream-window-aggregator](./examples/tasks/stream-window-aggregator/TASK.md) | Hard | Lock-free 编程、事件时间语义 |
| 2 | [bitmap-vector-fix](./examples/tasks/bitmap-vector-fix/TASK.md) | Medium | C++ 调试、边界条件 |
| 3 | [stream-ingest-deadlock](./examples/tasks/stream-ingest-deadlock/TASK.md) | Hard | Python 并发、锁语义 |
| 4 | [distributed-chaos-system](./examples/tasks/distributed-chaos-system/TASK.md) | Extreme | 分布式系统、非确定性行为 |
| 5 | [clickhouse-to-doris](./examples/tasks/clickhouse-to-doris/TASK.md) | Medium | 数据库 schema 迁移、索引优化 |

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
uv run harbor run -a oracle -p examples/tasks/clickhouse-to-doris

# 验证空 Agent（预期得分 0.0）
uv run harbor run -a nop -p examples/tasks/clickhouse-to-doris

# 查看评测结果
uv run harbor view jobs

# 运行所有任务
for task in examples/tasks/*/; do
    uv run harbor run -a oracle -p "$task"
done
```

### 验证 kimi-k2.5 API 测试

```bash
# 设置 Bailian API Key
export BAILIAN_API_KEY="your-api-key-here"

# 运行 API 测试（无需 Harbor）
cd examples/tasks/clickhouse-to-doris
python3 tests/test_kimi_migration.py

# 运行完整 benchmark
python3 app/gen_test_data.py --target ck --create-tables --run-queries
```

---

## 项目结构

```
examples/tasks/<task-name>/
├── task.toml          # 元数据
├── instruction.md     # Agent 可见的任务描述
├── environment/       # Docker 镜像定义
├── tests/             # 测试脚本
└── solution/          # Oracle 参考解法
```

详细技术分析见各任务目录下的 `TASK.md` 和 `FINAL_RESULTS.md`。

---

*最后更新：2026-04-23*
