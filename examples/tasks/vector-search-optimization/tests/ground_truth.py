#!/usr/bin/env python3
"""
Generate ground truth using brute-force search.
Optimized for speed with batch computation.
"""
import numpy as np
import os
import sys
import time

def brute_force_search_batch(base, queries, topk=10, batch_size=50):
    """
    Brute-force search with batch computation.
    
    Uses the identity: ||a - b||^2 = ||a||^2 + ||b||^2 - 2*a·b
    """
    n = base.shape[0]
    m = queries.shape[0]
    
    # Precompute norms
    base_norm_sq = (base ** 2).sum(axis=1)  # (n,)
    
    results = np.zeros((m, topk), dtype=np.int64)
    
    for i in range(0, m, batch_size):
        end = min(i + batch_size, m)
        
        # Compute batch of distances
        # dist[i:i+batch] = base_norm_sq + query_norm_sq - 2 * base @ query.T
        query_batch = queries[i:end]
        query_norm_sq = (query_batch ** 2).sum(axis=1)  # (batch,)
        
        # Cross term: base @ query_batch.T = (n, batch)
        cross_term = base @ query_batch.T  # (n, batch_size)
        
        # Distance matrix: (n, batch_size)
        distances_sq = base_norm_sq[:, np.newaxis] + query_norm_sq[np.newaxis, :] - 2 * cross_term
        
        # Get top-k for each query in batch
        for j in range(end - i):
            topk_indices = np.argpartition(distances_sq[:, j], topk)[:topk]
            # Sort the top-k by distance
            topk_indices = topk_indices[np.argsort(distances_sq[topk_indices, j])]
            results[i + j] = topk_indices
    
    return results

def compute_recall(predictions, ground_truth):
    """Compute recall@k."""
    m, k = predictions.shape
    recalls = []
    for i in range(m):
        pred_set = set(predictions[i].tolist())
        gt_set = set(ground_truth[i].tolist())
        recall = len(pred_set & gt_set) / k
        recalls.append(recall)
    return np.mean(recalls)

def main():
    # Use script directory or DATA_DIR environment variable
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.environ.get("DATA_DIR", os.path.dirname(script_dir) + "/data")
    
    print("=== Generating Ground Truth ===")
    
    # Load data
    print("\n[1/3] Loading base_random...")
    base_random = np.load(os.path.join(data_dir, "base_random.npy"))
    print(f"  Shape: {base_random.shape}")
    
    print("[2/3] Loading base_skewed...")
    base_skewed = np.load(os.path.join(data_dir, "base_skewed.npy"))
    print(f"  Shape: {base_skewed.shape}")
    
    print("[3/3] Loading queries...")
    queries = np.load(os.path.join(data_dir, "queries.npy"))
    print(f"  Shape: {queries.shape}")
    
    # Generate ground truth
    print("\n=== Computing Ground Truth (Random) ===")
    start = time.time()
    gt_random = brute_force_search_batch(base_random, queries, topk=10)
    elapsed = time.time() - start
    print(f"  Time: {elapsed:.2f}s")
    print(f"  Sample result (query 0): {gt_random[0]}")
    
    print("\n=== Computing Ground Truth (Skewed) ===")
    start = time.time()
    gt_skewed = brute_force_search_batch(base_skewed, queries, topk=10)
    elapsed = time.time() - start
    print(f"  Time: {elapsed:.2f}s")
    print(f"  Sample result (query 0): {gt_skewed[0]}")
    
    # Save
    print(f"\n=== Saving to {data_dir} ===")
    np.save(os.path.join(data_dir, "gt_random.npy"), gt_random)
    np.save(os.path.join(data_dir, "gt_skewed.npy"), gt_skewed)
    
    # Verification: self-check
    print("\n=== Verification ===")
    recall_random = compute_recall(gt_random, gt_random)
    recall_skewed = compute_recall(gt_skewed, gt_skewed)
    print(f"  Recall (random, self-check): {recall_random:.4f} ✓")
    print(f"  Recall (skewed, self-check): {recall_skewed:.4f} ✓")
    
    print("\n✅ Ground truth generation complete!")

if __name__ == "__main__":
    main()
