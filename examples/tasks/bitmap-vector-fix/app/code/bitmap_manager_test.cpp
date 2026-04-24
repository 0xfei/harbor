#include <iostream>
#include <cassert>
#include <string>
#include <vector>
#include "bitmap_manager.h"

// ── 简单断言工具 ──────────────────────────────────────────────────────────────
static int g_pass = 0;
static int g_fail = 0;

#define CHECK(expr) do { \
    if (expr) { std::cout << "  [PASS] " #expr "\n"; ++g_pass; } \
    else      { std::cout << "  [FAIL] " #expr " (line " << __LINE__ << ")\n"; ++g_fail; } \
} while(0)

// ── 测试 loadBitMap ───────────────────────────────────────────────────────────
void test_load_bitmap() {
    std::cout << "\n[test_load_bitmap]\n";
    BitMapManager mgr;

    // 初始 size 为 0
    CHECK(mgr.size() == 0);

    // loadBitMap 加载主键维度（index 0），按 \n 分割
    mgr.loadBitMap("apple\nbanana\ncherry");
    CHECK(mgr.size() == 1);

    // 已加载的 key 应该存在
    CHECK(mgr.exists({{"apple",  0}}));
    CHECK(mgr.exists({{"banana", 0}}));
    CHECK(mgr.exists({{"cherry", 0}}));

    // 未加载的 key 不存在
    CHECK(!mgr.exists({{"grape",  0}}));
    CHECK(!mgr.exists({{"",       0}}));
}

// ── 测试 addBitMap ────────────────────────────────────────────────────────────
void test_add_bitmap() {
    std::cout << "\n[test_add_bitmap]\n";
    BitMapManager mgr;

    // 先 load 主键维度
    mgr.loadBitMap("u1\nu2\nu3");
    CHECK(mgr.size() == 1);

    // 增加第 1 个额外维度（index 1）：城市
    std::vector<std::string> values1 = {"beijing\nshanghai"};
    std::vector<std::string> tags1   = {"city"};
    mgr.addBitMap(values1, tags1);
    CHECK(mgr.size() == 2);

    // 增加第 2 个额外维度（index 2）：设备
    std::vector<std::string> values2 = {"ios\nandroid"};
    std::vector<std::string> tags2   = {"device"};
    mgr.addBitMap(values2, tags2);
    CHECK(mgr.size() == 3);

    // 城市维度查询
    CHECK(mgr.exists({{"beijing",  1}}));
    CHECK(mgr.exists({{"shanghai", 1}}));
    CHECK(!mgr.exists({{"tokyo",   1}}));

    // 设备维度查询
    CHECK(mgr.exists({{"ios",     2}}));
    CHECK(mgr.exists({{"android", 2}}));
    CHECK(!mgr.exists({{"windows",2}}));
}

// ── 测试 exists：多维度 AND 语义 ──────────────────────────────────────────────
void test_exists_multi_dim() {
    std::cout << "\n[test_exists_multi_dim]\n";
    BitMapManager mgr;

    mgr.loadBitMap("u1\nu2");                                  // dim 0
    mgr.addBitMap({"vip\nnormal"},    {"level"});              // dim 1
    mgr.addBitMap({"ios\nandroid"},   {"device"});             // dim 2

    // 所有维度都命中 → true
    CHECK(mgr.exists({{"u1",      0}, {"vip",     1}, {"ios",     2}}));
    // 有一个维度不命中 → false
    CHECK(!mgr.exists({{"u1",     0}, {"vip",     1}, {"windows", 2}}));
    // 主键不存在 → false
    CHECK(!mgr.exists({{"u999",   0}, {"vip",     1}, {"ios",     2}}));
    // 空列表 → true（vacuous truth：没有条件不满足）
    CHECK(mgr.exists({}));
}

// ── 测试 size ─────────────────────────────────────────────────────────────────
void test_size() {
    std::cout << "\n[test_size]\n";
    BitMapManager mgr;
    CHECK(mgr.size() == 0);

    mgr.loadBitMap("a");
    CHECK(mgr.size() == 1);

    mgr.addBitMap({"x"}, {"tag1"});
    CHECK(mgr.size() == 2);

    mgr.addBitMap({"y", "z"}, {"tag2", "tag3"});
    CHECK(mgr.size() == 4);
}

// ── 测试 grow 从空状态开始（触发 size_t 下溢）──────────────────────────────
void test_grow_from_empty() {
    std::cout << "\n[test_grow_from_empty]\n";
    BitMapManager mgr;

    // 关键测试：从空状态直接 addBitMap（不先 loadBitMap）
    // 这会触发 grow(old_bit_depth=0, new_bit_depth=values.size())
    // 如果 grow() 中循环写成 for (size_t i = new-1; i >= 0; i--)
    // 则 i 永远 >= 0（size_t 无符号），导致死循环或越界

    std::vector<std::string> values = {"x\ny\nz"};
    std::vector<std::string> tags   = {"test_dim"};

    // 如果 size_t 下溢 bug 存在，这里会卡住或崩溃
    mgr.addBitMap(values, tags);
    CHECK(mgr.size() == 1);

    // 验证数据正确写入
    CHECK(mgr.exists({{"x", 0}}));
    CHECK(mgr.exists({{"y", 0}}));
    CHECK(mgr.exists({{"z", 0}}));
    CHECK(!mgr.exists({{"w", 0}}));

    // 再添加一个维度，验证 grow 多次调用正确
    mgr.addBitMap({"a\nb"}, {"dim2"});
    CHECK(mgr.size() == 2);
    CHECK(mgr.exists({{"a", 1}}));
    CHECK(mgr.exists({{"b", 1}}));
}

// ── 测试连续多次 addBitMap（验证 grow 参数累加）─────────────────────────────
void test_consecutive_add() {
    std::cout << "\n[test_consecutive_add]\n";
    BitMapManager mgr;

    // 先 load 主键
    mgr.loadBitMap("user1\nuser2");
    CHECK(mgr.size() == 1);

    // 连续添加 5 个维度
    for (int i = 0; i < 5; i++) {
        std::string tag = "dim" + std::to_string(i);
        mgr.addBitMap({"v1\nv2"}, {tag});
    }
    CHECK(mgr.size() == 6);

    // 验证每个维度都能正确查询
    CHECK(mgr.exists({{"user1", 0}}));
    CHECK(mgr.exists({{"v1", 1}}));
    CHECK(mgr.exists({{"v1", 5}}));
    CHECK(!mgr.exists({{"v1", 6}}));  // 越界检查
}

// ── 测试大量维度（压力测试 grow）─────────────────────────────────────────────
void test_many_dimensions() {
    std::cout << "\n[test_many_dimensions]\n";
    BitMapManager mgr;

    mgr.loadBitMap("id1\nid2");

    // 添加 50 个维度
    for (int i = 0; i < 50; i++) {
        std::string tag = "dim" + std::to_string(i);
        mgr.addBitMap({"val\n" + tag}, {tag});
    }
    CHECK(mgr.size() == 51);

    // 验证第一个和最后一个维度
    CHECK(mgr.exists({{"id1", 0}}));
    CHECK(mgr.exists({{"val", 1}}));
    CHECK(mgr.exists({{"val", 50}}));
    CHECK(!mgr.exists({{"val", 51}}));
}

// ── main ──────────────────────────────────────────────────────────────────────
int main() {
    std::cout << "=== BitMapManager Tests ===\n";
    test_load_bitmap();
    test_add_bitmap();
    test_exists_multi_dim();
    test_size();
    test_grow_from_empty();       // 新增：测试 size_t 下溢
    test_consecutive_add();        // 新增：测试 grow 参数累加
    test_many_dimensions();        // 新增：压力测试

    std::cout << "\n=== Results ===\n";
    std::cout << "  PASS: " << g_pass << "\n";
    std::cout << "  FAIL: " << g_fail << "\n";
    return g_fail > 0 ? 1 : 0;
}
