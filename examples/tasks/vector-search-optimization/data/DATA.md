# Vector Search Test Data

This directory contains generated test data for the vector search optimization task.

## Data Files (Not in Git)

Large binary files are excluded from git:

| File | Size | Description |
|------|------|-------------|
| `base_random.npy` | 488 MB | 1,000,000 × 128 float32 vectors (uniform distribution) |
| `base_skewed.npy` | 488 MB | 999,746 × 128 float32 vectors (skewed cluster distribution) |
| `queries.npy` | 500 KB | 1,000 × 128 float32 query vectors |
| `gt_random.npy` | 78 KB | Ground truth indices (1000 × 10) for random distribution |
| `gt_skewed.npy` | 78 KB | Ground truth indices (1000 × 10) for skewed distribution |
| `*.bin` | ~1 GB | Binary format for C++ consumption |

## Generate Data

Run the following commands to generate test data:

```bash
cd examples/tasks/vector-search-optimization

# 1. Generate numpy data (30 seconds)
python3 data/generate_data.py

# 2. Generate ground truth (20 seconds)
python3 tests/ground_truth.py

# 3. Convert to binary format
python3 app/convert.py data/base_random.npy data/base_random.bin
python3 app/convert.py data/base_skewed.npy data/base_skewed.bin
python3 app/convert.py data/queries.npy data/queries.bin
```

## Data Characteristics

### Random Distribution
- 100 clusters with uniform random centroids
- 10,000 vectors per cluster (even distribution)
- Norm range: [1.07, 1.92]
- Standard clustering algorithms work well

### Skewed Distribution
- 100 clusters but top 10 clusters contain 50% of vectors
- Large clusters: 50,000 vectors each (σ=0.05)
- Small clusters: ~5,500 vectors each (σ=0.2)
- Norm range: [0.92, 3.19]
- Challenges standard clustering approaches

## Query Generation

Queries are sampled from `base_random.npy` to ensure they belong to existing clusters. This makes the task realistic (queries match the training distribution).

```python
query_indices = np.random.choice(len(base_random), 1000, replace=False)
queries = base_random[query_indices]
```

## Ground Truth

Ground truth is computed using exact brute-force search:

```python
# For each query
distances = ((base - query) ** 2).sum(axis=1)
topk_indices = np.argsort(distances)[:10]
```

This ensures 100% accuracy for the oracle solution.

## Total Size

- Numpy files: ~977 MB
- Binary files: ~1,024 MB
- Total: ~2 GB

**Do not commit these files to git.** Use `.gitignore` to exclude them.
