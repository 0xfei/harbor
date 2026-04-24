/**
 * Baseline C++ implementation of brute-force vector search.
 * 
 * This is a REFERENCE implementation - slow but correct.
 * Performance: ~30-60 seconds for 1M vectors × 1000 queries
 * 
 * Compile: g++ -std=c++11 -O2 -Wall -o search search.cpp
 * Usage: ./search <base.bin> <queries.bin> <output.bin> <topk>
 */

#include <vector>
#include <fstream>
#include <algorithm>
#include <cstdint>
#include <string>
#include <iostream>
#include <cassert>
#include <cmath>

/**
 * Load float vectors from binary file.
 * File format: raw little-endian float32 values
 * 
 * @param path Path to binary file
 * @return Vector of floats (n * d elements)
 */
std::vector<float> load_vectors(const std::string& path) {
    std::ifstream file(path, std::ios::binary | std::ios::ate);
    if (!file) {
        throw std::runtime_error("Cannot open file: " + path);
    }
    
    const auto file_size = file.tellg();
    file.seekg(0, std::ios::beg);
    
    const size_t num_floats = file_size / sizeof(float);
    std::vector<float> data(num_floats);
    
    file.read(reinterpret_cast<char*>(data.data()), file_size);
    file.close();
    
    return data;
}

/**
 * Compute squared L2 distance between two vectors.
 * 
 * @param a First vector pointer
 * @param b Second vector pointer
 * @param d Dimension
 * @return Squared Euclidean distance
 */
inline float compute_distance_sq(const float* a, const float* b, int64_t d) {
    float dist = 0.0f;
    for (int64_t i = 0; i < d; ++i) {
        const float diff = a[i] - b[i];
        dist += diff * diff;
    }
    return dist;
}

/**
 * Brute-force vector search - O(n*m*d) time complexity.
 * 
 * This is slow but guaranteed to be correct.
 * 
 * @param base Base vectors (n * d elements)
 * @param queries Query vectors (m * d elements)
 * @param n Number of base vectors
 * @param m Number of queries
 * @param d Dimension (must be 128)
 * @param topk Number of nearest neighbors to return
 * @return Vector of m rows, each containing topk indices
 */
std::vector<std::vector<int64_t>> search(
    const std::vector<float>& base,
    const std::vector<float>& queries,
    int64_t n,
    int64_t m,
    int64_t d,
    int64_t topk
) {
    // Validate dimensions
    assert(static_cast<int64_t>(base.size()) == n * d);
    assert(static_cast<int64_t>(queries.size()) == m * d);
    
    std::vector<std::vector<int64_t>> results;
    results.reserve(m);
    
    // Process each query
    for (int64_t q_idx = 0; q_idx < m; ++q_idx) {
        const float* query = queries.data() + q_idx * d;
        
        // Compute distances to all base vectors
        std::vector<std::pair<float, int64_t>> distances;
        distances.reserve(n);
        
        for (int64_t b_idx = 0; b_idx < n; ++b_idx) {
            const float* base_vec = base.data() + b_idx * d;
            const float dist = compute_distance_sq(query, base_vec, d);
            distances.emplace_back(dist, b_idx);
        }
        
        // Partial sort to get top-k
        std::partial_sort(
            distances.begin(),
            distances.begin() + topk,
            distances.end(),
            [](const auto& a, const auto& b) {
                return a.first < b.first;
            }
        );
        
        // Extract top-k indices
        std::vector<int64_t> topk_indices;
        topk_indices.reserve(topk);
        for (int64_t i = 0; i < topk; ++i) {
            topk_indices.push_back(distances[i].second);
        }
        
        results.push_back(std::move(topk_indices));
    }
    
    return results;
}

/**
 * Main entry point.
 * 
 * Usage: ./search <base.bin> <queries.bin> <output.bin> <topk>
 */
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
    
    // Configuration (must match data)
    const int64_t n = 1000000;  // base vectors
    const int64_t m = 1000;    // queries
    const int64_t d = 128;     // dimension
    
    std::cout << "Loading base vectors from " << base_path << "...\n";
    auto base = load_vectors(base_path);
    std::cout << "Loaded " << base.size() << " floats (" 
              << base.size() * sizeof(float) / (1024.0 * 1024.0) << " MB)\n";
    
    std::cout << "Loading query vectors from " << query_path << "...\n";
    auto queries = load_vectors(query_path);
    std::cout << "Loaded " << queries.size() << " floats\n";
    
    std::cout << "Running search (n=" << n << ", m=" << m 
              << ", d=" << d << ", topk=" << topk << ")...\n";
    auto results = search(base, queries, n, m, d, topk);
    
    std::cout << "Writing results to " << output_path << "...\n";
    std::ofstream out(output_path, std::ios::binary);
    for (const auto& row : results) {
        out.write(reinterpret_cast<const char*>(row.data()), 
                  row.size() * sizeof(int64_t));
    }
    out.close();
    
    std::cout << "Done! Output size: " << results.size() << " x " << topk << "\n";
    
    return 0;
}
