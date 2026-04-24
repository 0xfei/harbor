/**
 * Optimized vector search using min-heap.
 * 
 * Key optimizations:
 * 1. Cache-friendly memory access (sequential scan)
 * 2. Min-heap to track top-k smallest distances
 * 3. Multi-threading for parallel query processing
 * 
 * Performance target: < 1.5s for 1M vectors × 1000 queries
 */

#include <vector>
#include <fstream>
#include <algorithm>
#include <cstdint>
#include <string>
#include <iostream>
#include <cassert>
#include <cmath>
#include <queue>
#include <thread>

// Configuration
constexpr int64_t DIM = 128;
constexpr int64_t TOPK = 10;
constexpr int NUM_THREADS = 4;

/**
 * Load float vectors from binary file.
 */
std::vector<float> load_vectors(const std::string& path) {
    std::ifstream file(path, std::ios::binary | std::ios::ate);
    if (!file) {
        throw std::runtime_error("Cannot open: " + path);
    }
    
    const auto file_size = file.tellg();
    file.seekg(0, std::ios::beg);
    
    const size_t num_floats = file_size / sizeof(float);
    std::vector<float> data(num_floats);
    
    file.read(reinterpret_cast<char*>(data.data()), file_size);
    return data;
}

/**
 * Compute squared L2 distance with loop unrolling.
 */
inline float distance_sq(const float* a, const float* b) {
    float d0 = 0.0f, d1 = 0.0f, d2 = 0.0f, d3 = 0.0f;
    
    for (int64_t i = 0; i < DIM; i += 4) {
        const float diff0 = a[i] - b[i];
        const float diff1 = a[i+1] - b[i+1];
        const float diff2 = a[i+2] - b[i+2];
        const float diff3 = a[i+3] - b[i+3];
        
        d0 += diff0 * diff0;
        d1 += diff1 * diff1;
        d2 += diff2 * diff2;
        d3 += diff3 * diff3;
    }
    
    return d0 + d1 + d2 + d3;
}

/**
 * Process a batch of queries using brute-force with optimizations.
 */
void process_batch(
    const float* base,
    const float* queries,
    int64_t n,
    int64_t start_query,
    int64_t end_query,
    std::vector<std::vector<int64_t>>& results
) {
    for (int64_t q_idx = start_query; q_idx < end_query; ++q_idx) {
        const float* query = queries + q_idx * DIM;
        
        // Use a vector to store {distance, index} pairs
        std::vector<std::pair<float, int64_t>> topk_pairs;
        topk_pairs.reserve(TOPK + 1);
        
        // Scan all base vectors
        for (int64_t b_idx = 0; b_idx < n; ++b_idx) {
            const float* base_vec = base + b_idx * DIM;
            const float dist = distance_sq(query, base_vec);
            
            if (topk_pairs.size() < TOPK) {
                topk_pairs.push_back({dist, b_idx});
                // Keep heap property (max-heap)
                std::push_heap(topk_pairs.begin(), topk_pairs.end());
            } else if (dist < topk_pairs[0].first) {
                // Replace largest element
                std::pop_heap(topk_pairs.begin(), topk_pairs.end());
                topk_pairs.back() = {dist, b_idx};
                std::push_heap(topk_pairs.begin(), topk_pairs.end());
            }
        }
        
        // Sort by distance (ascending)
        std::sort(topk_pairs.begin(), topk_pairs.end());
        
        // Extract indices
        results[q_idx].reserve(TOPK);
        for (const auto& p : topk_pairs) {
            results[q_idx].push_back(p.second);
        }
    }
}

/**
 * Main search function.
 */
std::vector<std::vector<int64_t>> search(
    const std::vector<float>& base,
    const std::vector<float>& queries,
    int64_t n,
    int64_t m,
    int64_t d,
    int64_t topk
) {
    assert(static_cast<int64_t>(base.size()) == n * d);
    assert(static_cast<int64_t>(queries.size()) == m * d);
    assert(d == DIM);
    assert(topk == TOPK);
    
    std::vector<std::vector<int64_t>> results(m);
    
    if (m < 100) {
        process_batch(base.data(), queries.data(), n, 0, m, results);
    } else {
        std::vector<std::thread> threads;
        const int64_t batch_size = (m + NUM_THREADS - 1) / NUM_THREADS;
        
        for (int t = 0; t < NUM_THREADS; ++t) {
            const int64_t start = t * batch_size;
            const int64_t end = std::min(start + batch_size, m);
            
            if (start < m) {
                threads.emplace_back(
                    process_batch,
                    base.data(),
                    queries.data(),
                    n,
                    start,
                    end,
                    std::ref(results)
                );
            }
        }
        
        for (auto& t : threads) {
            t.join();
        }
    }
    
    return results;
}

int main(int argc, char* argv[]) {
    if (argc != 5) {
        std::cerr << "Usage: " << argv[0] 
                  << " <base.bin> <queries.bin> <output.bin> <topk>\n";
        return 1;
    }
    
    const std::string base_path = argv[1];
    const std::string query_path = argv[2];
    const std::string output_path = argv[3];
    const int64_t topk = std::stoll(argv[4]);
    
    const int64_t n = 1000000;
    const int64_t m = 1000;
    const int64_t d = 128;
    
    std::cout << "Loading data...\n";
    auto base = load_vectors(base_path);
    auto queries = load_vectors(query_path);
    
    std::cout << "Running search...\n";
    auto results = search(base, queries, n, m, d, topk);
    
    std::cout << "Writing output...\n";
    std::ofstream out(output_path, std::ios::binary);
    for (const auto& row : results) {
        out.write(reinterpret_cast<const char*>(row.data()),
                  row.size() * sizeof(int64_t));
    }
    
    std::cout << "Done!\n";
    return 0;
}
