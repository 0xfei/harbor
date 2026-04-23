# stream-ingest-deadlock — 流式数据摄入死锁修复

| 属性 | 值 |
|------|----|
| **难度** | Hard |
| **类别** | 系统编程 / 并发 / Python |
| **编程语言** | Python 3.10 |
| **容器资源** | 4 CPU / 2 GB RAM / 无外网 |
| **Agent 超时** | 900 秒 |
| **Verifier 超时** | 60 秒 |

---

## 任务描述

给定一个**多线程数据摄入系统**，处理 10 万条事件并写入 WAL（Write-Ahead Log）。系统存在**死锁 bug**，导致程序卡住无法完成。

**目标**：修复死锁问题，使程序在 15 秒内处理完 10 万条事件，且：
- 无重复提交
- 每个 shard 内顺序正确（seq 递增）
- 内存峰值 < 500 MB

---

## 死锁分析

### 原始代码结构

```python
class Dispatcher:
    def __init__(self):
        self.lock_a = threading.Lock()  # 保护队列
        self.lock_b = threading.Lock()  # 保护 commit

    def producer(self):
        with self.lock_a:           # 持有 lock_a
            self.q.put(evt)          # 队列满时阻塞 ← 死锁点

    def consumer(self):
        with self.lock_b:           # 持有 lock_b
            evt = self.q.get()
            self.commit(evt)         # 内部尝试获取 lock_a

    def commit(self, evt):
        with self.lock_a:           # 等待 lock_a ← 死锁点
            with self.lock_b:       # 已持有 lock_b
                ...
```

### 死锁触发条件

1. 队列接近满（Queue(maxsize=64)）
2. Producer 持有 `lock_a`，调用 `q.put()` 阻塞等待空间
3. Consumer 持有 `lock_b`，调用 `q.get()` 后在 `commit()` 中等待 `lock_a`
4. **循环等待**：
   - Producer 等待 Consumer 消费（需要队列空间）
   - Consumer 等待 Producer 释放 `lock_a`
5. **结果**：永久阻塞

---

## 修复要点

| 问题 | 修复 |
|------|------|
| 多锁嵌套导致死锁 | 只用一把锁保护共享状态 |
| Queue 操作外层加锁多余 | Queue 本身线程安全，无需外部锁 |
| commit 中双重锁获取 | 只在 commit 中获取单锁 |
| 顺序检查逻辑错误 | `seq <= order[s]` 应改为 `seq > order[s]` |

### 正确实现要点

```python
class Dispatcher:
    def __init__(self):
        self.q = queue.Queue(maxsize=256)  # 适当增大
        self.lock = threading.Lock()       # 单锁保护 commit 状态
        ...

    def producer(self):
        for line in f:
            evt = json.loads(line)
            self.q.put(evt)                 # 无需外层锁
        self.done = True

    def consumer(self):
        while not self.done or not self.q.empty():
            try:
                evt = self.q.get(timeout=0.1)
            except queue.Empty:
                continue
            self.commit(evt)

    def commit(self, evt):
        with self.lock:                     # 单锁保护
            if self.dedup.check(evt["id"]):
                s = evt["shard"]
                if evt["seq"] > self.order[s]:  # 顺序检查
                    self.order[s] = evt["seq"]
                    self.wal.append(evt["id"])
                    self.processed += 1
```

---

## 评分维度

| 维度 | 权重 | 说明 |
|------|------|------|
| `correctness` | **0.60** | 处理 100000 条事件，无重复，顺序正确 |
| `runtime` | 0.15 | 运行时间 < 15 秒 |
| `memory` | 0.15 | 峰值 RSS < 500 MB |
| `no_crash` | 0.10 | 进程正常退出（无死锁/异常） |

---

## 难度设计要点

1. **隐蔽性**：死锁只在队列满时触发，小数据集可能通过
2. **误导性**：代码有两把锁，看起来"更安全"，实际是陷阱
3. **并发陷阱**：多线程并发问题难以复现和调试
4. **约束叠加**：禁用 asyncio/multiprocessing，限制解决方案

---

## 运行结果（实际）

| Agent | Harbor 得分 | 说明 |
|-------|------------|------|
| **oracle**（已修复版本） | **1.000** | 全部通过 ✅ |
| **nop**（空 Agent） | **TIMEOUT** | 死锁，verifier 超时 ✅ |
| **kimi-k2.5**（API 测试） | **TIMEOUT** | 识别出双锁问题，但修复不完整 ⚠️ |

### kimi-k2.5 测试详情

API 调用结果显示：
- ✅ 正确识别出应该使用单锁
- ✅ 移除了双锁嵌套
- ✅ 知道 Queue 操作不需要外部锁
- ❌ 但实际运行仍超时（可能还有其他并发问题）

**结论：kimi-k2.5 无法完整修复此死锁问题，成功率 < 30%**

---

## 文件结构

```
stream-ingest-deadlock/
├── task.toml              # 任务元数据
├── instruction.md         # 题目说明（Agent 可见）
├── TASK.md                # 本文件
├── app/
│   ├── main.py            # 入口
│   ├── dispatcher.py      # 有 bug 的调度器
│   ├── dedup.py           # 去重器
│   └── wal.py             # WAL 实现
├── data/
│   └── events.jsonl       # 测试数据（需生成）
├── tests/
│   ├── test.sh            # 判题入口
│   └── test_state.py      # pytest 评分逻辑
└── solution/
    └── solve.sh           # Oracle 解法
```
