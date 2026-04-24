#!/usr/bin/env python3
"""
Generate test data for vector search optimization task.

Creates:
- base_random.npy: 1M vectors with uniform cluster distribution
- base_skewed.npy: 1M vectors with skewed cluster distribution  
- queries.npy: 1000 query vectors (sampled from base)
"""
import numpy as np
import os
import sys

def generate_random_data(n_clusters=100, vectors_per_cluster=10000, dim=128, seed=42):
    """Generate uniformly distributed clustered vectors."""
    np.random.seed(seed)
    
    # Generate random unit-norm centroids
    centroids = np.random.randn(n_clusters, dim).astype(np.float32)
    centroids = centroids / np.linalg.norm(centroids, axis=1, keepdims=True)
    
    # Generate vectors around each centroid
    base = []
    for i in range(n_clusters):
        # Add Gaussian noise around centroid
        noise = np.random.randn(vectors_per_cluster, dim).astype(np.float32) * 0.1
        cluster_vectors = centroids[i:i+1] + noise
        base.append(cluster_vectors)
    
    base = np.vstack(base)
    return base

def generate_skewed_data(n_clusters=100, dim=128, total_vectors=1000000, seed=43):
    """Generate skewed cluster distribution.
    
    - Top 10 clusters: 50,000 vectors each (500,000 total = 50%)
    - Remaining 90 clusters: ~5,556 vectors each (500,000 total)
    """
    np.random.seed(seed)
    
    # Generate random unit-norm centroids
    centroids = np.random.randn(n_clusters, dim).astype(np.float32)
    centroids = centroids / np.linalg.norm(centroids, axis=1, keepdims=True)
    
    base = []
    
    # Top 10 clusters: 50,000 vectors each
    large_cluster_size = 50000
    for i in range(10):
        noise = np.random.randn(large_cluster_size, dim).astype(np.float32) * 0.05
        cluster_vectors = centroids[i:i+1] + noise
        base.append(cluster_vectors)
    
    # Remaining 90 clusters: share 500,000 vectors
    remaining_vectors = total_vectors - 500000
    small_cluster_size = remaining_vectors // (n_clusters - 10)
    
    for i in range(10, n_clusters):
        # Add some random variation
        size = small_cluster_size + np.random.randint(-500, 500)
        if size <= 0:
            size = 1000
        noise = np.random.randn(size, dim).astype(np.float32) * 0.2
        cluster_vectors = centroids[i:i+1] + noise
        base.append(cluster_vectors)
    
    base = np.vstack(base)
    return base

def generate_queries(base, n_queries=1000, seed=44):
    """Generate query vectors by sampling from base."""
    np.random.seed(seed)
    
    n = len(base)
    indices = np.random.choice(n, n_queries, replace=False)
    queries = base[indices]
    
    return queries, indices

def main():
    # Use current directory or DATA_DIR environment variable
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.environ.get("DATA_DIR", script_dir)
    os.makedirs(data_dir, exist_ok=True)
    
    print("=== Generating Vector Search Test Data ===")
    print(f"Output directory: {data_dir}")
    
    # Generate random distribution
    print("\n[1/3] Generating random distribution...")
    base_random = generate_random_data(
        n_clusters=100,
        vectors_per_cluster=10000,
        dim=128,
        seed=42
    )
    print(f"  Shape: {base_random.shape}")
    print(f"  Memory: {base_random.nbytes / 1024**2:.2f} MB")
    print(f"  Norm range: [{np.linalg.norm(base_random, axis=1).min():.3f}, {np.linalg.norm(base_random, axis=1).max():.3f}]")
    
    # Generate skewed distribution
    print("\n[2/3] Generating skewed distribution...")
    base_skewed = generate_skewed_data(
        n_clusters=100,
        dim=128,
        total_vectors=1000000,
        seed=43
    )
    print(f"  Shape: {base_skewed.shape}")
    print(f"  Memory: {base_skewed.nbytes / 1024**2:.2f} MB")
    print(f"  Norm range: [{np.linalg.norm(base_skewed, axis=1).min():.3f}, {np.linalg.norm(base_skewed, axis=1).max():.3f}]")
    
    # Generate queries (from random distribution)
    print("\n[3/3] Generating queries...")
    queries, query_indices = generate_queries(base_random, n_queries=1000, seed=44)
    print(f"  Shape: {queries.shape}")
    print(f"  Memory: {queries.nbytes / 1024**2:.2f} MB")
    
    # Save files
    print(f"\n=== Saving to {data_dir} ===")
    np.save(os.path.join(data_dir, "base_random.npy"), base_random)
    np.save(os.path.join(data_dir, "base_skewed.npy"), base_skewed)
    np.save(os.path.join(data_dir, "queries.npy"), queries)
    np.save(os.path.join(data_dir, "query_indices.npy"), query_indices)
    
    print("\n=== Summary ===")
    print(f"base_random.npy: {base_random.shape} ({base_random.nbytes / 1024**3:.3f} GB)")
    print(f"base_skewed.npy: {base_skewed.shape} ({base_skewed.nbytes / 1024**3:.3f} GB)")
    print(f"queries.npy: {queries.shape} ({queries.nbytes / 1024**2:.2f} MB)")
    
    print("\n✅ Data generation complete!")

if __name__ == "__main__":
    main()
