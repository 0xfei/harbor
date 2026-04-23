# bitmap-vector-fix — 多维 Hash 过滤器 Bug 修复

| 属性 | 值 |
|------|----|
| **难度** | Medium |
| **类别** | 调试 / C++ |
| **编程语言** | C++11 |
| **容器资源** | 2 CPU / 512 MB RAM / 无 GPU / 无外网 |
| **Agent 超时** | 900 秒 |
| **Verifier 超时** | 60 秒 |

---

## 任务描述

给定一个编译通过但运行时崩溃的 `BitMapManager` 实现（多维字符串哈希过滤器），
修复 `bitmap_manager.cpp` 中的 bug，使所有测试通过。

**核心功能**：
- `loadBitMap(values)` — 加载主键维度（index 0）
- `addBitMap(values, tags)` — 批量增加维度
- `exists({(string, dim_index), ...})` — 检查多个维度是否都包含指定 key
- `size()` — 返回当前维度数

---

## 强制约束

| 约束 | 说明 |
|------|------|
| **只修改 bitmap_manager.cpp** | 其他 .h / .cpp 文件只读 |
| **禁用第三方库** | 仅 C++11 标准库 |
| **最小修复原则** | 不重构整体架构 |

---

## 评分维度

| 维度 | 权重 | 说明 |
|------|------|------|
| `correctness` | **1.0** | 所有测试通过（24/24 PASS），exit code = 0 |

> 本题采用全有或全无评分：要么全部通过得 1.0，否则按通过比例计算。

---

## 难度设计要点

题目包含 **3 个典型 C++ bug**：

1. **`grow()` 中 `reserve()` vs `resize()`**：
   - 原代码用 `reserve()` 增加容量但未改变 `size()`
   - 之后用 `operator[]` 写入超出 size 的位置，触发 UB → segfault

2. **`grow()` 中循环方向错误**：
   - 原代码 `for (size_t i = new_bit_depth - 1; i >= old_bit_depth; i--)`
   - 当 `old_bit_depth = 0` 时，`size_t` 下溢导致死循环或越界

3. **`addBitMap()` 参数传给 `grow()` 错误**：
   - 原代码 `grow(values.size())` 应该是 `grow(old_bit_depth + values.size())`

这三个 bug 都在 `bitmap_manager.cpp` 中，是典型的 C++ 初学者错误。

---

## 运行结果（实际）

| Agent | Harbor 得分 | 说明 |
|-------|------------|------|
| **oracle**（已修复版本） | **1.000** | 24/24 PASS ✅ |
| **nop**（空 Agent） | **0.000** | 无输出 ✅ |
| **kimi-k2.5**（实际测试） | **100%** | ⚠️ 远超预期（43/43 全通过） |

> ⚠️ **设计反思**：原预期 kimi-k2.5 成功率 <30%，但实际测试显示 **至少 60% 成功率**（3/5 完全通过）。这道题对现代大模型来说太简单了。

### 为什么 kimi-k2.5 表现超出预期？

1. **bug 类型典型**：`reserve()` vs `resize()`、`size_t` 下溢是常见 C++ 错误模式
2. **代码量小**：约 70 行代码，模型可完整阅读
3. **错误信息明确**：segfault 清晰指向内存访问问题

### 为什么 kimi-k2.5 表现超出预期？

1. **bug 类型典型**：`reserve()` vs `resize()`、`size_t` 下溢是常见 C++ 错误模式
2. **代码量小**：约 70 行代码，模型可完整阅读
3. **错误信息明确**：segfault 清晰指向内存访问问题
4. **测试覆盖清晰**：新增测试（如 `test_grow_from_empty`）虽然增加了 size_t 下溢检测，但模型仍能一次性修复

### 如何真正达到 <30% 成功率？

建议改进方向：

1. **增加代码量到 300+ 行**：分散模型注意力
2. **使用更隐蔽的 bug**：
   - 并发问题（竞态条件）
   - 内存泄漏（需 valgrind 才能发现）
   - 边界条件（只在特定输入下触发）
3. **添加干扰代码**：无关逻辑、误导性注释
4. **限制可见信息**：只提供模糊错误描述，不给完整错误堆栈
5. **多文件项目**：需跨多个文件理解和修改

---

## 文件结构

```
bitmap-vector-fix/
├── task.toml              # 任务元数据
├── instruction.md         # 题目说明（Agent 读取）
├── TASK.md                # 本文件
├── cpp-files/             # 原始有 bug 的代码（只读）
│   ├── bitmap.h
│   ├── hash.h
│   ├── bitmap_manager.h
│   ├── bitmap_manager.cpp   ← 有 bug 的版本
│   ├── bitmap_manager_test.cpp
│   └── CMakeLists.txt
├── environment/
│   └── Dockerfile         # Ubuntu 22.04 + g++
├── tests/
│   ├── test.sh            # 判题入口
│   ├── bitmap_manager_test.cpp  # 与 cpp-files 中相同
│   ├── bitmap.h
│   ├── hash.h
│   ├── bitmap_manager.h
│   └── bitmap_manager_buggy.cpp  # 有 bug 的备份
└── solution/
    ├── solve.sh           # Oracle 解法（应用修复）
    ├── bitmap_manager_fixed.cpp  # 修复后的版本
    └── bitmap_manager.cpp        # 有 bug 的原始版本
```

---

## 评分逻辑（test.sh）

1. 将有 bug 的原始代码复制到 `/app/`（如果 agent 未写）
2. 编译：`g++ -std=c++11 -o bitmap_manager_test bitmap_manager_test.cpp bitmap_manager.cpp`
3. 运行测试，解析输出中的 `[PASS]` / `[FAIL]`
4. 计算奖励：`reward = pass_count / (pass_count + fail_count)`

---

## 为什么设计为 < 30% 成功率

- **多 bug 定位难度**：模型需要找到 3 个不同的 bug，而非一处
- **UB 表现不一致**：`reserve()` + `operator[]` 在不同平台可能表现不同
- **size_t 下溢陷阱**：无符号整数循环下溢是 C++ 典型错误
- **代码阅读量适中**：约 70 行 cpp 文件，但逻辑较密
