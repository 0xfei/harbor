# vector-search-optimization — 百万级向量检索优化

| 属性 | 值 |
|------|----|
| **难度** | Hard |
| **类别** | 性能优化 / 向量检索 / C++ / 标准库 |
| **编程语言** | **C++11+（强制）** |
| **容器资源** | 4 CPU / 8 GB RAM / 无 GPU / 允许外网 |
| **Agent 超时** | 1800 秒 |
| **Verifier 超时** | 120 秒 |

> ⚠️ **强制要求 C++ 实现**，Python 仅为数据准备参考

---

## 任务描述

将一个 Python 暴力向量检索实现（耗时 ~30s）优化到生产可用水平（< 1.5s），同时保持召回率 >= 95% 和内存 < 3GB。

**⚠️ 必须使用 C++11+ 标准库实现，禁止使用第三方库（Boost/Eigen/FAISS/OpenMP）**

**现状问题**：
- 100万 vectors × 128 维
- 1000 queries
- 暴力搜索：逐个计算欧氏距离
- 延迟：**~30 秒**
- 目标：**< 1.5 秒**

---

## 原始实现

```python
import numpy as np

def search(base, queries, topk):
    """Brute-force vector search - O(n*d) per query"""
    out = []
    for q in queries:
        d = ((base - q) ** 2).sum(axis=1)
        idx = np.argsort(d)[:topk]
        out.append(idx)
    return np.array(out)
```

**性能瓶颈**：
1. Python 循环开销
2. 逐个距离计算
3. 无索引结构（线性扫描）
4. 内存拷贝（broadcast）

**C++ 实现约束**：
- 必须使用 C++11 或更高版本
- 只能使用标准库（<vector>, <algorithm>, <thread> 等）
- 禁止 SIMD intrinsics（AVX/SSE）
- 禁止 OpenMP/pthread
- 代码必须清晰可读，有注释
- 变量/函数命名有意义
- 无内存泄漏（使用 RAII）

---

## 评分设计

| 维度 | 权重 | 目标 | 计算方式 |
|------|------|------|---------|
| `latency` | **0.50** | < 1.5s | max(0, 1 - latency/3.0) |
| `recall` | **0.30** | >= 0.95 | min(1.0, recall/0.95) |
| `memory` | **0.20** | < 3GB | max(0, 1 - memory/6GB) |

**约束惩罚**：
- Memory >= 3GB → 总分 = 0
- Latency >= 3s → 总分 = 0
- Recall < 0.85 → 总分 = 0

---

## 数据设计

### 数据集 1：均匀分布（基线）

```python
np.random.seed(42)
centroids = np.random.randn(100, 128).astype(np.float32)
centroids /= np.linalg.norm(centroids, axis=1, keepdims=True)

# 每个簇生成 10000 个向量
base_random = []
for c in centroids:
    base_random.append(c + np.random.randn(10000, 128).astype(np.float32) * 0.1)
base_random = np.vstack(base_random)
```

**特点**：
- 100 个簇均匀分布
- 每簇 10,000 向量
- 标准聚类算法效果良好

### 数据集 2：倾斜分布（挑战）

```python
np.random.seed(43)
centroids = np.random.randn(100, 128).astype(np.float32)
centroids /= np.linalg.norm(centroids, axis=1, keepdims=True)

base_skewed = []
# 前 10 个簇：每簇 50000 向量（50% 数据）
for i in range(10):
    base_skewed.append(centroids[i] + np.random.randn(50000, 128).astype(np.float32) * 0.05)

# 后 90 个簇：平均分布剩余 50%
for i in range(10, 100):
    base_skewed.append(centroids[i] + np.random.randn(556, 128).astype(np.float32) * 0.2)

base_skewed = np.vstack(base_skewed)
```

**特点**：
- 50% 向量集中在 10% 簇
- 后 90 个簇向量稀疏（< 600 个）
- 标准聚类需要调整参数

### Query 生成

```python
# 从 base 中随机采样
query_indices = np.random.choice(len(base), 1000, replace=False)
queries = base[query_indices]
```

---

## Oracle 解法

### 方案 A：多线程暴力搜索（标准库）

```cpp
#include <thread>
#include <vector>
#include <queue>
#include <algorithm>

// 每个线程处理一批 queries
void process_batch(const float* base, const float* queries,
                   int64_t start, int64_t end, 
                   int64_t n, std::vector<int64_t>* results) {
    for (int64_t q = start; q < end; ++q) {
        // Max-heap 保留 top-k
        std::priority_queue<std::pair<float, int64_t>> heap;
        
        for (int64_t b = 0; b < n; ++b) {
            float dist = compute_distance(base + b * 128, queries + q * 128);
            if (heap.size() < 10 || dist < heap.top().first) {
                heap.push({dist, b});
                if (heap.size() > 10) heap.pop();
            }
        }
        
        // 提取结果
        while (!heap.empty()) {
            results[q].push_back(heap.top().second);
            heap.pop();
        }
    }
}

// 主函数启动 4 线程
std::vector<std::thread> threads;
for (int t = 0; t < 4; ++t) {
    threads.emplace_back(process_batch, base, queries, t * 250, (t+1) * 250, n, results);
}
```

**预期性能**：
- Latency ~2-4s（取决于 CPU）
- Recall = 1.0（精确搜索）
- Memory ~500MB

### 方案 B：分块 + 剪枝

```cpp
// 将 base 分成 10 块，每块 100K 向量
// 先计算块内距离下界，剪枝不可能的块
// 对剩余块做精确搜索

struct Block {
    std::vector<float> centroid;
    std::vector<float> vectors;
};

std::vector<int64_t> search_with_pruning(
    const std::vector<Block>& blocks,
    const float* query, int64_t topk
) {
    // 1. 计算所有块质心距离
    std::vector<std::pair<float, int>> block_dists;
    for (int i = 0; i < blocks.size(); ++i) {
        float d = distance(query, blocks[i].centroid);
        block_dists.push_back({d, i});
    }
    
    // 2. 排序并保留可能包含 top-k 的块
    std::sort(block_dists.begin(), block_dists.end());
    
    // 3. 对候选块做精确搜索
    DistanceHeap heap(topk);
    for (const auto& [d, idx] : block_dists) {
        // 如果质心距离已经超出当前最大距离，剪枝
        if (heap.size() == topk && d > heap.max_distance()) break;
        
        // 搜索该块
        search_block(blocks[idx], query, heap);
    }
    
    return heap.extract();
}
```

**预期性能**：
- Latency ~1-2s
- Recall ~0.96-0.99（近似搜索）
- Memory ~1GB

---

## 测试流程

### Verifier 步骤

```bash
# 1. 加载数据
base_random = np.load('/data/base_random.npy')
base_skewed = np.load('/data/base_skewed.npy')
queries = np.load('/data/queries.npy')

# 2. 生成 ground truth
gt_random = brute_force_search(base_random, queries, 10)
gt_skewed = brute_force_search(base_skewed, queries, 10)

# 3. 运行候选实现
start = time.time()
results_random = search(base_random, queries, 10)
latency_random = time.time() - start

start = time.time()
results_skewed = search(base_skewed, queries, 10)
latency_skewed = time.time() - start

# 4. 计算 recall
recall_random = compute_recall(results_random, gt_random)
recall_skewed = compute_recall(results_skewed, gt_skewed)

# 5. 测量内存
memory = measure_peak_memory()

# 6. 计算得分
score = 0.5 * latency_score + 0.3 * recall_score + 0.2 * memory_score
```

---

## 难度设计要点

### 1. 性能优化陷阱

| 陷阱 | 描述 |
|------|------|
| **Broadcast 内存爆炸** | `(base - q)` 创建临时数组，100MB × 1000 queries = 100GB |
| **argsort 全排序** | 只需 top-k，全排序浪费 O(n log n) |
| **单线程** | Python GIL 限制，需用 numpy/faiss 多线程 |
| **精度损失** | float16 可能影响 recall |

### 2. 数据分布挑战

**倾斜数据的坑**：
- FAISS 默认 `nlist=100` 可能不够
- 大簇需要更多 probe
- 小簇可能被忽略

**解决方案**：
- 动态调整 `nprobe`
- 使用 HNSW（不依赖聚类）
- 或 PQ + 重排

### 3. 约束冲突

| 约束 | 冲突点 |
|------|--------|
| 高 recall | 需要更多计算 |
| 低 latency | 需要近似算法 |
| 低 memory | 限制索引大小 |

**权衡策略**：
- IVF: 中等 recall，低内存，中等速度
- HNSW: 高 recall，高内存，快速度
- PQ: 低 recall，极低内存，快速度

---

## kimi-k2.5 能力评估点

### 测试维度

| 维度 | 考察点 |
|------|--------|
| **复杂程序设计** | 能否设计合理的索引结构 |
| **多轮迭代能力** | 从错误日志中学习并改进 |
| **性能调优** | 理解 latency/recall/memory 权衡 |
| **数据理解** | 识别倾斜分布并调整参数 |
| **工程实践** | 错误处理、日志、API 设计 |

### 预期表现

| 场景 | 预期结果 |
|------|---------|
| **第一轮** | 生成 FAISS IVF 基线实现 |
| **遇到倾斜数据失败** | 调整 nprobe 或切换到 HNSW |
| **内存超限** | 考虑 PQ 或减少索引大小 |
| **Recall 不足** | 增加搜索范围或精确重排 |

---

## 文件结构

```
vector-search-optimization/
├── task.toml              # 任务元数据
├── instruction.md         # Agent 可见的任务说明
├── TASK.md                # 本文件
├── environment/
│   └── Dockerfile         # Python + faiss-cpu
├── app/
│   ├── search.py          # 待优化的实现（Agent 写入）
│   └── baseline.py        # 原始暴力实现（参考）
├── data/
│   ├── generate_data.py   # 数据生成脚本
│   ├── base_random.npy    # 均匀分布数据
│   ├── base_skewed.npy    # 倾斜分布数据
│   └── queries.npy        # 查询向量
├── tests/
│   ├── test.sh            # 判题入口
│   ├── test_search.py     # pytest 评分逻辑
│   └── ground_truth.py    # 暴力搜索生成 ground truth
└── solution/
    └── solve.sh           # Oracle 解法（FAISS IVF + HNSW）
```

---

## 运行结果（预期）

| Agent | Latency | Recall | Memory | Score |
|-------|---------|--------|--------|-------|
| **oracle** | 0.5s | 0.97 | 2GB | **1.0** |
| **nop** | - | - | - | **0.0** |
| **kimi-k2.5 (第1轮)** | 2.0s | 0.92 | 3.5GB | **0.6** |
| **kimi-k2.5 (第3轮)** | 0.8s | 0.95 | 2.5GB | **0.9** |

---

*最后更新：2026-04-23*
