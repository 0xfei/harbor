# Harbor 评测任务说明

> 本目录（`examples/tasks/`）收录了用于考察 **顶级 Coding Agent** 综合能力的系统级编程评测题。  
> 每道题均基于 [Harbor](https://github.com/convergence-ai/harbor) 评测框架，支持一键运行、自动评分。

---

## 目录结构约定

每道题是一个独立子目录，遵循 Harbor 标准结构：

```
examples/tasks/<task-name>/
├── task.toml              # 任务元数据（名称、资源限制、超时等）
├── instruction.md         # 题目说明（Agent 读取的原始任务描述）
├── TASK.md                # 任务详情说明（本地阅读用，不进入容器）
├── environment/
│   └── Dockerfile         # 评测容器镜像定义
├── tests/
│   ├── test.sh            # 判题入口（verifier 调用）
│   ├── test_state.py      # pytest 多维度评分逻辑
│   └── conftest.py        # pytest hook（汇总分数到 scores.json）
├── solution/
│   ├── solve.sh           # Oracle 参考解法入口
│   └── ...                # oracle 实现、数据生成器等
└── run_kimi_eval.sh       # （可选）快速 API 静态评分脚本
```

---

## 快速运行

**前提条件：**
- [Harbor CLI](https://github.com/convergence-ai/harbor) 已安装（`uv tool install harbor-ai`）
- Docker 或 Podman Desktop 已启动

```bash
# 克隆本仓库，进入 harbor 目录
cd /path/to/harbor

# 用 Oracle 参考解法验证题目可用（预期得分 1.0）
uv run harbor run -a oracle -p examples/tasks/<task-name>

# 用空 Agent 验证基准（预期得分 0.0）
uv run harbor run -a nop -p examples/tasks/<task-name>

# 查看评测结果
uv run harbor view jobs
```

> **Podman 用户**：需配置 docker shim，详见「环境配置」小节。

---

## 任务列表

| # | 任务目录 | 难度 | 类别 | 详情 |
|---|----------|------|------|------|
| 1 | [stream-window-aggregator](./stream-window-aggregator/TASK.md) | Hard | 系统编程 / 并发 | 流式滑动窗口聚合引擎，lock-free + 精确事件时间语义 |
| 2 | [bitmap-vector-fix](./bitmap-vector-fix/TASK.md) | Medium | 调试 / C++ | 修复 `BitMapManager` 中 `grow()` 的 3 个典型 bug |
| 3 | [stream-ingest-deadlock](./stream-ingest-deadlock/TASK.md) | Hard | 系统编程 / Python | 修复多线程数据摄入系统中的死锁问题 |
| 4 | [distributed-chaos-system](./distributed-chaos-system/TASK.md) | Extreme | 分布式系统 / 非确定性 | 修复分布式计费系统的非确定性行为 |

> 新增任务时，在此表格追加一行，并在对应目录下创建 `TASK.md`。

---

## 环境配置（Podman Desktop）

若未安装 Docker Desktop，可用 Podman Desktop 替代：

```bash
# 1. 安装并启动 Podman Machine
brew install podman
podman machine init
podman machine start

# 2. 获取 socket 路径
podman machine inspect | grep APISocket

# 3. 设置 DOCKER_HOST
export DOCKER_HOST="unix:///path/to/podman-machine-default-api.sock"

# 4. 安装 Docker Compose v2 插件
mkdir -p ~/.docker/cli-plugins
curl -SL "https://github.com/docker/compose/releases/download/v2.36.0/docker-compose-darwin-aarch64" \
     -o ~/.docker/cli-plugins/docker-compose
chmod +x ~/.docker/cli-plugins/docker-compose

# 5. 创建 docker shim（让 harbor 调用 docker 时走 podman）
cat > /opt/homebrew/bin/docker << 'EOF'
#!/bin/sh
export DOCKER_HOST="unix:///path/to/podman-machine-default-api.sock"
if [ "$1" = "compose" ]; then
    shift
    exec "$HOME/.docker/cli-plugins/docker-compose" "$@"
fi
exec podman "$@"
EOF
chmod +x /opt/homebrew/bin/docker
```

---

## 题目方向规划

本评测集按能力维度分档设计，覆盖从基础编程到全链路诊断的完整能力谱系：

### Level 1：编程语言基础与典型误解

考察对特定编程语言的语法、语义、运行时行为的精确理解。

| 题目方向 | 语言 | 考察点 |
|---------|------|--------|
| 类型系统陷阱 | Rust/C++/Go | 所有权/生命周期/接口断言 |
| 异步模型理解 | Python/JS/Go | 事件循环/协程调度/GIL |
| 内存模型 | C/C++ | 未定义行为/序列点/求值顺序 |
| 标准库行为 | 各语言 | 边界条件/迭代器失效/隐式转换 |

### Level 2：系统级缺陷诊断

考察对编译型语言中资源管理、并发正确性的理解。

| 题目方向 | 语言 | 考察点 |
|---------|------|--------|
| 内存泄漏 | C/C++/Rust | 分配未释放/循环引用/RAII 违反 |
| 死锁与竞态 | C++/Go/Java | 锁顺序/原子操作/CAS 循环 |
| 安全风险 | C/C++ | 缓冲区溢出/格式化字符串/注入 |
| 异常安全 | C++/Rust | 构造失败/析构顺序/资源泄漏 |

### Level 3：解释型语言特性

考察对解释型语言的模块系统、执行模型、运行时行为的理解。

| 题目方向 | 语言 | 考察点 |
|---------|------|--------|
| 包引用关系 | Python/JS/TS | 循环依赖/符号解析/导出可见性 |
| 执行顺序 | Python/JS | 定义提升/导入时机/懒加载 |
| 运行时行为 | Python/Ruby/JS | 元编程/反射/描述符协议 |
| 依赖冲突 | Node.js/Python | 版本锁定/符号覆盖/命名空间污染 |

### Level 4：跨文件/跨模块理解

考察在大型项目中定位和修复分散在多个文件的 bug 的能力。

| 题目方向 | 场景 | 考察点 |
|---------|------|--------|
| 配置驱动 bug | 微服务配置 | 环境差异/默认值陷阱/优先级 |
| 接口契约违反 | API 边界 | 类型不匹配/版本兼容/序列化 |
| 模块间耦合 | 大型单体 | 隐式依赖/全局状态/初始化顺序 |
| 构建系统集成 | CMake/Bazel | 依赖传递/条件编译/增量构建 |

### Level 5：黑盒/白盒故障诊断

仅依赖外部观测（日志、输入输出）定位问题，无需直接访问代码。

| 题目方向 | 场景 | 考察点 |
|---------|------|--------|
| 日志分析 | 服务调试 | 错误模式识别/时序推断/根因定位 |
| 网络异常 | 分布式系统 | 超时/重试/连接池耗尽/DNS 问题 |
| 存储故障 | 数据库 | 死锁/锁等待/索引失效/事务回滚 |
| 全链路问题 | 微服务 | 熔断/降级/级联失败/雪崩 |
| 资源竞争 | 云原生 | CPU 抢占/OOM/磁盘 IO 等待 |

---

### 已规划题目（欢迎 PR）

按上述方向，计划实现的题目：

**Level 1-2（编译型语言）：**
- [ ] `lock-free-queue` — 无锁 MPMC 队列，考察 CAS 循环 + ABA 问题
- [ ] `memory-allocator` — 实现 `malloc`/`free`，考察内存对齐与碎片整理
- [ ] `simd-matrix-mul` — AVX2 矩阵乘法，考察 SIMD intrinsics 与内存布局优化

**Level 2（并发与安全）：**
- [ ] `epoll-http-server` — 基于 epoll 的 HTTP/1.1 服务器，考察 I/O 多路复用
- [ ] `thread-pool-bug` — 线程池实现中的资源泄漏与竞态条件

**Level 3（解释型语言）：**
- [ ] `python-circular-import` — 循环依赖导致的初始化顺序问题
- [ ] `node-module-conflict` — npm 依赖冲突与版本锁定陷阱

**Level 4（跨模块理解）：**
- [ ] `config-driven-bug` — 多环境配置导致的行为差异
- [ ] `api-contract-violation` — 前后端接口契约不一致

**Level 5（黑盒诊断）：**
- [ ] `distributed-deadlock` — 跨服务分布式锁死锁诊断（仅提供日志）
- [ ] `cascading-failure` — 微服务雪崩故障分析（仅提供监控面板截图）
- [ ] `raft-log-replication` — 简化版 Raft 日志复制，考察分布式共识协议实现

**Level 6（高强度验证）：**
- [ ] `apache-analyser` — 目标是跑通主流 apache 项目，跟踪github修复记录，验证 ai 能否完成同样的任务
- [ ] `data-agent` — 跨各类数据库的数据迁移、sql优化等专项任务

---

*最后更新：2026-04-23*
