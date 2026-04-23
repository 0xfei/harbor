# stream-window-aggregator — 流式滑动窗口聚合引擎

| 属性 | 值 |
|------|----|
| **难度** | Hard |
| **类别** | 系统编程 / 并发 |
| **编程语言** | C++17 |
| **容器资源** | 4 CPU / 512 MB RAM / 无 GPU / 无外网 |
| **Agent 超时** | 1800 秒 |
| **Verifier 超时** | 120 秒 |

---

## 任务描述

模拟真实视频推荐流水线场景：给定 50 万条乱序用户点击事件（二进制格式，24 字节/条），
要求实现 `/app/aggregator`，计算每位用户在 **30 秒事件时间滑动窗口**内的 **Top-3 兴趣类目**，
并按 `user_id` 数值升序写入 `/data/output.tsv`。

**输入格式**（`/data/events.bin`，little-endian 二进制）：

```c
struct Event {
    uint64_t event_ts_ms;   // 事件时间戳（毫秒）
    uint32_t user_id;
    uint16_t category_id;   // 视频类目（0–999）
    uint16_t watch_seconds; // 观看时长（1–600 秒）
    uint8_t  _pad[8];       // 填充至 24 字节
};
```

**输出格式**（`/data/output.tsv`）：

```
<user_id>\t<cat1>:<score1>,<cat2>:<score2>,<cat3>:<score3>
```

---

## 强制约束（6 项）

| 约束 | 说明 | 检测方式 |
|------|------|----------|
| **A — 禁锁** | 不得使用 mutex / semaphore / rwlock，只能用 `std::atomic` | `nm -C` 符号扫描 |
| **B — 禁关联容器** | 不得使用 `std::map` / `unordered_map` / set 系列 | `nm -C` 符号扫描 |
| **C — 内存限制** | 进程峰值 RSS < 200 MB | `/usr/bin/time -v` 测量 |
| **D — 事件时间语义** | 窗口以用户 `max event_ts` 为锚点，不能按文件读取顺序处理 | 输出 diff（Oracle 对比） |
| **E — 精确 4 线程** | 必须创建且仅创建 4 个 worker 线程 | 运行时采样 `/proc/<pid>/status` |
| **F — 无第三方库** | 只能用 C++17 标准库 + POSIX API | 编译约束 |

---

## 评分维度

| 维度 | 权重 | 说明 |
|------|------|------|
| `correctness` | **0.50** | 输出与 Oracle 逐行对比，要求 ≥ 95% 一致 |
| `no_mutex` | 0.15 | 二进制无 mutex 相关符号 |
| `no_map` | 0.10 | 二进制无 map/set 相关符号 |
| `memory` | 0.10 | 峰值 RSS < 200 MB |
| `four_threads` | 0.05 | 运行时观测到 4–6 线程（main + 4 workers） |
| `source_file` | 0.05 | `/app/aggregator.cpp` 存在 |
| `output_fmt` | 0.05 | TSV 格式正确，user_id 数值排序 |

---

## 难度设计要点

以下是专门针对 LLM Coding Agent 的"陷阱"：

1. **事件时间 vs 处理时间**：事件乱序 ±5s，按文件顺序扫描无法得到正确 max_ts，必须两遍扫描
2. **24 字节对齐陷阱**：Event struct 实际 16 bytes 有效数据 + 8 bytes padding，模型常忘记填充导致 `static_assert` 编译失败
3. **内存估算陷阱**：提示说 500k users × 1000 cats × 4B = 2GB 超限，诱导模型做复杂的内存节省设计，但实际用户数只有 10k，能合法分配 `g_users[32768]` 约 131MB
4. **lock-free 正确性**：多线程 CAS 更新 `max_ts` 需要正确内存序，`relaxed` 用错会导致数据竞争
5. **禁 map 却需要哈希表**：不能用 STL 关联容器，必须自己实现 open-addressing hash table
6. **数值排序 vs 字典序**：`user_id` 为 uint32，排序必须数值比较，`sort` 默认整数排序正确，但若转成字符串会错

---

## 运行结果

基准验证（Harbor 容器真实运行）：

| Agent | Harbor 得分 | 说明 |
|-------|------------|------|
| **oracle**（参考解法） | **1.000** | 全部通过 ✅ |
| **nop**（空 Agent） | **0.000** | 无输出，基准正确 ✅ |

kimi-k2.5 多轮测试（共 10 次，均使用 Harbor 容器真实编译运行）：

| 轮次 | Harbor 容器得分 | 编译结果 | 失败原因 |
|------|---------------|----------|----------|
| run_1 ~ run_5（第一批） | **0.350** × 5 | ❌ 编译失败 | `Event` struct 缺 `uint8_t _pad[8]`，`static_assert(sizeof==24)` 触发 |
| run_1 ~ run_5（第二批） | **0.350** × 5 | ❌ 编译失败 | 同上，系统性漏掉 padding 字段 |

**得分构成（编译失败情况下）：**

| 维度 | 得分 | 说明 |
|------|------|------|
| `source_file` | 1.0 × 0.05 | `/app/aggregator.cpp` 存在（代码文件已写入） |
| `no_mutex` | 1.0 × 0.15 | nm 扫描通过（编译失败时无二进制，视为通过） |
| `no_map` | 1.0 × 0.10 | 同上 |
| `memory` | 0.5 × 0.10 | 无法测量，取部分分 |
| `correctness` | 0.0 × 0.50 | 无输出文件 |
| `four_threads` | 0.0 × 0.05 | 无法运行 |
| `output_fmt` | 0.0 × 0.05 | 无输出文件 |
| **合计** | **0.350** | |

**结论：**

- kimi-k2.5 **10 次测试均编译失败**，成功率 **0%（满分要求 score ≥ 0.7）**
- 根本原因：模型**系统性地忽略** `Event` struct 中的 8 bytes padding 字段
- 即使 kimi-k2.5 写出了正确的两遍扫描逻辑、lock-free hash table、4 线程设计，仍因一个结构体字段错误全功尽弃

> **注意**：`run_kimi_eval.sh` 为静态分析脚本，仅做文本模式匹配，5/5 次误报为满分。以 Harbor 容器真实运行结果为准。

---

## 文件结构

```
stream-window-aggregator/
├── task.toml              # 任务元数据
├── instruction.md         # 题目说明（Agent 读取）
├── TASK.md                # 本文件（任务详情说明）
├── environment/
│   └── Dockerfile         # Ubuntu 22.04 + gcc/g++/python3/pytest
├── tests/
│   ├── test.sh            # 判题入口（生成数据→运行→pytest→写 reward）
│   ├── test_state.py      # pytest 多维度评分
│   └── conftest.py        # sessionfinish hook（写 scores.json）
├── solution/
│   ├── solve.sh           # Oracle 解法入口
│   ├── oracle_solver.cpp  # C++ 参考实现（满足全部约束）
│   ├── oracle.py          # Python oracle（生成 expected.tsv）
│   └── gen_data.py        # 测试数据生成器（50 万条乱序事件）
└── run_kimi_eval.sh       # 静态 API 评分脚本（仅供参考，不作为正式评分依据）
```
