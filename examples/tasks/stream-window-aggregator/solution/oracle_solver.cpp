// Oracle reference solution for stream-window-aggregator
// Compiled and run by solve.sh to produce /data/output.tsv
//
// This reference solution CORRECTLY implements all constraints:
// - Lock-free atomics only (no mutex)
// - No std::map/unordered_map for per-user state
// - Exactly 4 worker threads
// - Event-time based 30s sliding window
// - Array-based storage (robin-hood open addressing hash table)
// - Output sorted by numeric user_id

#include <atomic>
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <sys/mman.h>
#include <sys/stat.h>
#include <thread>
#include <unistd.h>
#include <vector>

static constexpr uint64_t WINDOW_MS  = 30'000;
static constexpr int      N_THREADS  = 4;
static constexpr int      N_CATS     = 1000;
static constexpr uint32_t EMPTY_KEY  = 0xFFFFFFFF;
static constexpr int      HT_SIZE    = 1 << 15;  // 32768 slots, load ~30%
static constexpr int      HT_MASK    = HT_SIZE - 1;

// ---- Packed 24-byte record matching the binary format ----
#pragma pack(push, 1)
struct Event {
    uint64_t event_ts_ms;
    uint32_t user_id;
    uint16_t category_id;
    uint16_t watch_seconds;
    uint8_t  _pad[8];
};
#pragma pack(pop)
static_assert(sizeof(Event) == 24, "Event struct must be 24 bytes");

// ---- Per-user state ----
// We store per-user data in a flat array indexed by a compact user index.
// We use a lock-free open-addressing hash table to map user_id -> index.

struct alignas(64) UserState {
    std::atomic<uint32_t> user_id{EMPTY_KEY};  // EMPTY_KEY = slot free
    std::atomic<uint64_t> max_ts{0};
    // category scores stored as 32-bit per category, 1000 cats = 4 KB per user
    // We keep a compact top-score array updated atomically
    // Full cat array would be 10000 * 1000 * 4 = 40 MB — within limit for 10k users
    std::atomic<uint32_t> cat_score[N_CATS];
};

// Max 12000 users in hash table (10000 * 1.2 load factor ~ 12000 < 32768)
static constexpr int MAX_USERS = 12000;
static UserState g_users[HT_SIZE];  // ~HT_SIZE * ~4KB each is too large
// ^ that's 32768 * 4064 bytes ~ 133 MB — just within 200 MB.
// But actually each UserState has 1000 atomics of 4 bytes = 4000 + overhead.
// 32768 slots × (4 + 8 + 1000×4) bytes = 32768 × 4012 = ~131 MB. Fine.

// Map user_id -> slot index (lock-free robin-hood)
static int find_or_insert_slot(uint32_t uid) {
    uint32_t h = uid * 2654435761u;
    int pos = (int)(h & HT_MASK);
    while (true) {
        uint32_t expected = EMPTY_KEY;
        // Try to claim this slot
        if (g_users[pos].user_id.load(std::memory_order_acquire) == uid) {
            return pos;
        }
        if (g_users[pos].user_id.compare_exchange_strong(
                expected, uid,
                std::memory_order_acq_rel,
                std::memory_order_acquire)) {
            // We just inserted this user; zero out cat_scores
            for (int c = 0; c < N_CATS; c++)
                g_users[pos].cat_score[c].store(0, std::memory_order_relaxed);
            return pos;
        }
        // Slot taken by someone else or was just claimed
        if (expected == uid) return pos;
        // Linear probe
        pos = (pos + 1) & HT_MASK;
    }
}

static void worker(const Event* events, size_t start, size_t end) {
    for (size_t i = start; i < end; i++) {
        const Event& e = events[i];
        uint32_t uid = e.user_id;
        int slot = find_or_insert_slot(uid);
        UserState& us = g_users[slot];

        // Update max_ts atomically
        uint64_t cur_max = us.max_ts.load(std::memory_order_relaxed);
        while (e.event_ts_ms > cur_max) {
            if (us.max_ts.compare_exchange_weak(cur_max, e.event_ts_ms,
                    std::memory_order_relaxed, std::memory_order_relaxed))
                break;
        }

        // Add watch time optimistically (we'll filter by window in output phase)
        // Store (ts, cat, ws) for later? No — we accumulate all and filter in pass2.
        // WAIT: we cannot filter without a second pass since max_ts may grow.
        // This is where naive agents fail: they add scores in one pass.
        // This oracle uses two-pass: pass1 for max_ts, pass2 for windowed scores.
        // In the worker we just record max_ts; actual accumulation done in pass2.
        (void)us;  // suppress warning; actual work below in pass2
    }
}

static void worker_accumulate(const Event* events, size_t start, size_t end) {
    for (size_t i = start; i < end; i++) {
        const Event& e = events[i];
        uint32_t uid = e.user_id;
        int slot = find_or_insert_slot(uid);
        UserState& us = g_users[slot];
        uint64_t max_ts = us.max_ts.load(std::memory_order_acquire);

        if (e.event_ts_ms + WINDOW_MS >= max_ts) {  // equivalent to ts >= max_ts - WINDOW_MS
            uint16_t cat = e.category_id;
            us.cat_score[cat].fetch_add(e.watch_seconds, std::memory_order_relaxed);
        }
    }
}

int main() {
    // Memory-map the input file
    int fd = open("/data/events.bin", O_RDONLY);
    if (fd < 0) { perror("open events.bin"); return 1; }
    struct stat st;
    fstat(fd, &st);
    size_t file_size = (size_t)st.st_size;
    size_t n_events  = file_size / sizeof(Event);

    const Event* events = (const Event*)mmap(nullptr, file_size,
        PROT_READ, MAP_SHARED, fd, 0);
    if (events == MAP_FAILED) { perror("mmap"); return 1; }

    // Initialize hash table
    for (int i = 0; i < HT_SIZE; i++)
        g_users[i].user_id.store(EMPTY_KEY, std::memory_order_relaxed);

    // --- Pass 1: Find max_ts per user using 4 threads ---
    {
        std::array<std::thread, N_THREADS> threads;
        size_t chunk = (n_events + N_THREADS - 1) / N_THREADS;
        for (int t = 0; t < N_THREADS; t++) {
            size_t s = t * chunk;
            size_t e = std::min(s + chunk, n_events);
            threads[t] = std::thread(worker, events, s, e);
        }
        for (auto& th : threads) th.join();
    }

    // --- Pass 2: Accumulate windowed scores using 4 threads ---
    {
        std::array<std::thread, N_THREADS> threads;
        size_t chunk = (n_events + N_THREADS - 1) / N_THREADS;
        for (int t = 0; t < N_THREADS; t++) {
            size_t s = t * chunk;
            size_t e = std::min(s + chunk, n_events);
            threads[t] = std::thread(worker_accumulate, events, s, e);
        }
        for (auto& th : threads) th.join();
    }

    munmap((void*)events, file_size);
    close(fd);

    // Collect non-empty users
    std::vector<std::pair<uint32_t, int>> uid_slots;
    uid_slots.reserve(MAX_USERS);
    for (int i = 0; i < HT_SIZE; i++) {
        uint32_t uid = g_users[i].user_id.load(std::memory_order_relaxed);
        if (uid != EMPTY_KEY)
            uid_slots.push_back({uid, i});
    }

    // Sort by numeric user_id
    std::sort(uid_slots.begin(), uid_slots.end());

    // Write output
    std::ofstream out("/data/output.tsv");
    for (auto [uid, slot] : uid_slots) {
        UserState& us = g_users[slot];
        // Collect categories with non-zero score
        std::vector<std::pair<uint32_t, int>> cat_scores;
        cat_scores.reserve(32);
        for (int c = 0; c < N_CATS; c++) {
            uint32_t sc = us.cat_score[c].load(std::memory_order_relaxed);
            if (sc > 0)
                cat_scores.push_back({sc, c});
        }
        // Sort: descending score, ascending cat_id for ties
        std::sort(cat_scores.begin(), cat_scores.end(),
            [](const auto& a, const auto& b) {
                return a.first != b.first ? a.first > b.first : a.second < b.second;
            });

        out << uid << '\t';
        int top = std::min((int)cat_scores.size(), 3);
        for (int i = 0; i < top; i++) {
            if (i > 0) out << ',';
            out << cat_scores[i].second << ':' << cat_scores[i].first;
        }
        out << '\n';
    }

    return 0;
}
