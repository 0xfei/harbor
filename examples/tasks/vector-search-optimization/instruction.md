# Vector Search Optimization (C++ Implementation Required)

## Background

You are working on a **recommendation system serving pipeline** that needs to perform real-time similarity search over a large vector database. The current Python implementation is too slow for production use.

**You must implement a C++ solution.** Python baseline is provided only for reference.

## Current Implementation (Reference Only)

```python
# This is Python reference code - DO NOT submit Python solution
import numpy as np

def search(base, queries, topk):
    """Brute-force vector search - TOO SLOW!"""
    out = []
    for q in queries:
        d = ((base - q) ** 2).sum(axis=1)
        idx = np.argsort(d)[:topk]
        out.append(idx)
    return np.array(out)
```

**Performance Problem:**
- Base: 1,000,000 vectors × 128 dimensions (float32)
- Queries: 1,000 vectors × 128 dimensions (float32)
- Current latency: **~30 seconds**
- Target latency: **< 1.5 seconds**

## Your Task

Implement `/app/search.cpp` with a C++ solution that:

### 1. Required API

```cpp
#include <vector>
#include <cstdint>

// Load binary data from file
std::vector<float> load_vectors(const std::string& path);

// Perform vector search
// Returns: indices of top-k nearest neighbors for each query
std::vector<std::vector<int64_t>> search(
    const std::vector<float>& base,    // n * d elements
    const std::vector<float>& queries, // m * d elements
    int64_t n,                          // number of base vectors
    int64_t m,                          // number of queries  
    int64_t d,                          // dimension (128)
    int64_t topk                        // k (10)
);
```

### 2. Technical Constraints

**MANDATORY:**
- **Language**: C++11 or later (C++11/14/17/20)
- **Libraries**: Standard library ONLY
  - Allowed: `<vector>`, `<algorithm>`, `<numeric>`, `<cmath>`, `<fstream>`, `<iostream>`, `<string>`, `<memory>`, `<thread>`, `<future>`, `<mutex>`, `<queue>`, `<limits>`, `<cassert>`
  - **FORBIDDEN**: Boost, Eigen, OpenBLAS, MKL, SIMD intrinsics (AVX/SSE), OpenMP, pthread, faiss, ann libraries
- **Compiler**: Must compile with `g++ -std=c++11 -O2`
- **Platform**: Linux x86_64

**Code Quality Requirements:**
- Readable variable/function names (no single-letter except loop counters)
- Comments explaining key algorithms
- Reasonable function decomposition (not one giant main)
- No memory leaks (use RAII or smart pointers)
- Clean compilation (no warnings with -Wall)

### 3. Performance Constraints

| Metric | Target | Hard Limit |
|--------|--------|------------|
| Latency | < 1.5s | < 3s (else score=0) |
| Memory | < 3GB | < 3GB (else score=0) |
| Recall@10 | >= 0.95 | >= 0.85 (else score=0) |

### 4. Data Format

**Binary files**: Little-endian float32, row-major order

```
base_random.npy  -> convert to base_random.bin (1000000 * 128 * 4 bytes)
base_skewed.npy  -> convert to base_skewed.bin (1000000 * 128 * 4 bytes)
queries.npy      -> convert to queries.bin (1000 * 128 * 4 bytes)
```

Helper conversion tool provided at `/app/convert.py`.

### 5. Optimization Strategies

Consider these approaches (non-exhaustive):

1. **Algorithmic**
   - K-D tree (but may not scale to 1M points)
   - Ball tree
   - LSH (Locality-Sensitive Hashing)
   - Product quantization
   - Hierarchical clustering

2. **Implementation**
   - Cache-friendly memory access patterns
   - Loop unrolling
   - Minimize allocations in hot path
   - Early termination strategies

3. **Approximate Search**
   - Coarse partitioning + fine search
   - Priority queue for top-k
   - Lower bound pruning

**Key insight**: Exact search is O(n*d) per query. For 1M vectors × 128 dims × 1000 queries = 128B operations. At ~1 GFLOP/s single-threaded, this takes ~128s. You need ~100x speedup!

## Input/Output Specification

### Input

- `/data/base_random.bin` - Random distribution (1000000 × 128 × float32)
- `/data/base_skewed.bin` - Skewed distribution (1000000 × 128 × float32)
- `/data/queries.bin` - Query vectors (1000 × 128 × float32)

### Output

Your program must:
1. Compile: `g++ -std=c++11 -O2 -Wall -o search search.cpp`
2. Run: `./search /data/base_random.bin /data/queries.bin output_random.bin 10`
3. Output format: For each query, write `topk` int64_t indices (binary)

### Example main()

```cpp
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
    
    // Configuration
    const int64_t n = 1000000;  // base vectors
    const int64_t m = 1000;    // queries
    const int64_t d = 128;    // dimension
    
    // Load data
    auto base = load_vectors(base_path);
    auto queries = load_vectors(query_path);
    
    // Search
    auto results = search(base, queries, n, m, d, topk);
    
    // Write results
    std::ofstream out(output_path, std::ios::binary);
    for (const auto& row : results) {
        out.write(reinterpret_cast<const char*>(row.data()), 
                  row.size() * sizeof(int64_t));
    }
    
    return 0;
}
```

## Scoring

| Metric | Weight | Target | Calculation |
|--------|--------|--------|-------------|
| Latency | 50% | < 1.5s | max(0, 1 - latency/3.0) |
| Recall | 30% | >= 0.95 | min(1.0, recall/0.95) |
| Memory | 20% | < 3GB | max(0, 1 - memory/6GB) |

**Code Quality Check:**
- Compilation warnings → -0.1 penalty
- Missing comments → -0.1 penalty
- Poor naming → -0.1 penalty
- Memory leaks → -0.2 penalty

## Testing Process

The verifier will:

1. **Compile** your `search.cpp`
   ```bash
   g++ -std=c++11 -O2 -Wall -o search search.cpp
   ```

2. **Run** on both distributions
   ```bash
   ./search /data/base_random.bin /data/queries.bin /tmp/out_random.bin 10
   ./search /data/base_skewed.bin /data/queries.bin /tmp/out_skewed.bin 10
   ```

3. **Compare** with ground truth
   - Compute recall@10 for each query set
   - Measure peak memory with `/usr/bin/time -v`
   - Record latency

4. **Score** final result

## Tips

- Start with brute-force baseline (should compile and run)
- Profile to find bottlenecks
- Consider approximation early (recall >= 0.95 acceptable)
- Test on both distributions - skewed may surprise you
- Use `<algorithm>`'s `nth_element` for partial sort
- Consider multi-threading with `<thread>` (but measure overhead)

## Common Mistakes

| Mistake | Symptom | Fix |
|---------|---------|-----|
| Reading wrong file size | Segfault or wrong results | Check file size matches expected |
| Float precision | Slightly wrong indices | Use `float` not `double` |
| Memory leak | Memory grows over runs | Use RAII/smart pointers |
| Cache miss | Slower than expected | Access memory sequentially |
| Thread contention | No speedup with threads | Minimize shared state |

## Files Provided

- `/app/convert.py` - Convert .npy to .bin format
- `/app/Makefile` - Build script (optional)
- `/app/baseline.cpp` - Brute-force reference (slow but correct)

Good luck! 🚀
