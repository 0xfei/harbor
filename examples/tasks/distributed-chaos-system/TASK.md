# distributed-chaos-system — 分布式系统非确定性修复

| 属性 | 值 |
|------|----|
| **难度** | Extreme |
| **类别** | 分布式系统 / 非确定性调试 |
| **编程语言** | Python 3.10 |
| **容器资源** | 4 CPU / 4 GB RAM |
| **Agent 超时** | 1200 秒 |
| **Verifier 超时** | 300 秒 |

---

## 任务描述

一个分布式计费系统在处理事件流时出现**非确定性行为**：每次运行产生的 ledger 结果都不同，无法通过 replay 重现，偶尔出现幽灵交易，有时记录丢失。

**目标**：修复系统使其在相同输入下产生**确定性输出**，同时保持以下约束：
- 必须保留 WAL（Write-Ahead Log）
- 必须保留 retry 逻辑（commit 可能失败）
- 必须支持 schema evolution
- replay 结果必须与首次运行一致

---

## 非确定性来源分析

### 问题 1：随机 mutation（mutation.py）

```python
class MutationEngine:
    def mutate_factor(self):
        return 1.0 if random.random() < 0.95 else 1.07  # 5% 概率改变金额
```

**影响**：每次运行时，事件金额可能被乘以 1.07，导致 ledger 总额不一致。

### 问题 2：概率性 commit（commit_graph.py）

```python
class CommitGraph:
    def commit(self):
        return random.random() < 0.97  # 3% 概率跳过事件
```

**影响**：约 1500 条事件被跳过，ledger_size 不稳定（48400-48600 之间波动）。

### 问题 3：replay 注入假事件（replay.py）

```python
def replay(events):
    if random.random() < 0.1:  # 10% 概率
        events.append({"user_id": -1, "amount": 999, ...})  # 幽灵交易
    return events
```

**影响**：replay 时可能注入不存在的交易，导致审计失败。

---

## 修复策略

### 约束理解

| 约束 | 含义 | 不能做的修改 |
|------|------|-------------|
| MUST keep WAL | 保留写前日志 | 不能删除 WAL 类 |
| MUST keep retry logic | commit 可能失败是合理的 | 不能让 commit() 总返回 True |
| MUST support schema evolution | 支持字段演化 | 不能删除 normalize_event |
| MUST be deterministic under replay | **关键约束** | 必须消除所有随机性 |

### 关键洞察

约束要求"replay 确定性"，但**不要求 commit 必须成功**。

正确理解：
1. **首次运行**时，可以重试直到 commit 成功
2. **replay** 时，应该只处理 WAL 中已确认的事件
3. 所有随机性必须在运行前固定（seed）或消除

---

## 评分维度

| 维度 | 权重 | 说明 |
|------|------|------|
| `determinism` | **0.40** | 两次运行结果完全相同 |
| `ledger_size` | 0.30 | 处理事件数 > 35000 |
| `no_phantom` | 0.20 | 无幽灵交易（user_id=-1） |
| `constraints` | 0.10 | 保留 WAL/retry/schema |

---

## 难度设计要点

1. **多层随机性**：需要定位 3 个不同的随机性来源
2. **约束理解**："保持 retry 逻辑"不等于"commit 必须失败"
3. **架构理解**：需要理解 WAL/Cache/Ledger 的协作关系
4. **测试复杂**：需要多次运行验证确定性

---

## 运行结果（实际测试）

| Agent | 结果 | 说明 |
|-------|------|------|
| **oracle** | ledger_size=50000, 确定性 | 全部通过 ✅ |
| **nop** | 非确定性 (48450-48553) | 每次不同 ✅ |
| **kimi-k2.5** | ✅ 成功修复 | 在明确描述问题后可正确修复 |

### kimi-k2.5 测试详情

**测试 1：隐晦问题描述**
- 结果：❌ 使用 hash 方案，过度复杂化
- 原因：问题不够清晰时，模型倾向于复杂方案

**测试 2：明确 root cause**
- 结果：✅ 正确修复所有三个文件
- 提供的修复：
  - `mutation.py`: `return 1.0`
  - `commit_graph.py`: `return True`
  - `replay.py`: `return events`

**结论：kimi-k2.5 在问题清晰时可以成功修复（预期成功率 > 50%）**

---

## 文件结构

```
distributed-chaos-system/
├── task.toml              # 任务元数据
├── instruction.md         # 题目说明（Agent 可见）
├── TASK.md                # 本文件
├── Dockerfile             # Python 3.10 环境
├── requirements.txt       # 依赖（无）
├── test.sh                # 判题入口
├── test_state.py          # pytest 测试
├── solve.sh               # Oracle 解法
├── app/
│   ├── main.py            # 入口
│   ├── billing.py         # 有 bug 的核心逻辑
│   ├── mutation.py        # 随机 mutation
│   ├── commit_graph.py    # 概率 commit
│   ├── replay.py          # 假事件注入
│   ├── schema.py          # 事件规范化
│   ├── wal.py             # 写前日志
│   ├── cache.py           # 用户余额缓存
│   └── ledger.py          # 最终账本
└── data/
    └── events.jsonl       # 测试数据（50000 条）
```
