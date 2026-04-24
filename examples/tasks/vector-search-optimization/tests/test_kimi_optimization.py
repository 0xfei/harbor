#!/usr/bin/env python3
"""
Multi-round iteration test for kimi-k2.5 on vector-search-optimization task.

This script:
1. Generates initial C++ implementation
2. Compiles and tests
3. Feeds errors/performance back to kimi
4. Iterates up to 30 rounds for optimization
5. Records scores and improvements
"""

import json
import os
import sys
import time
import subprocess
import tempfile
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from kimi_client import call_kimi as _call_kimi, KIMI_MODEL

# Configuration
MAX_ROUNDS = 30
API_TIMEOUT = 300
TARGET_LATENCY = 1.5
TARGET_RECALL = 0.95


def call_kimi_api(prompt: str) -> str:
    """Call Kimi API."""
    return _call_kimi([{"role": "user", "content": prompt}], temperature=0.7, max_tokens=8000, timeout=API_TIMEOUT)


def extract_code(response: str) -> Optional[str]:
    """Extract C++ code from markdown response."""
    import re
    
    # Try with language spec
    match = re.search(r"```(?:cpp|c\+\+)\n(.*?)\n```", response, re.DOTALL)
    if match:
        return match.group(1)
    
    # Try generic code block
    match = re.search(r"```\n(.*?)\n```", response, re.DOTALL)
    if match:
        return match.group(1)
    
    return None


def compile_cpp(code: str, output_path: str) -> tuple:
    """Compile C++ code."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False) as f:
        f.write(code)
        source_path = f.name
    
    try:
        result = subprocess.run(
            ["g++", "-std=c++11", "-O2", "-Wall", "-pthread",
             "-o", output_path, source_path],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            return True, ""
        else:
            return False, result.stderr
    except subprocess.TimeoutExpired:
        return False, "Compilation timeout"
    finally:
        os.unlink(source_path)


def run_search(executable: str, base_path: str, query_path: str, 
               output_path: str, topk: int = 10) -> tuple:
    """Run search executable and measure latency."""
    try:
        start = time.time()
        result = subprocess.run(
            [executable, base_path, query_path, output_path, str(topk)],
            capture_output=True,
            text=True,
            timeout=120
        )
        elapsed = time.time() - start
        
        if result.returncode == 0:
            return True, elapsed, ""
        else:
            return False, 0.0, result.stderr
    except subprocess.TimeoutExpired:
        return False, 0.0, "Execution timeout"


def compute_recall(pred_path: str, gt_path: str, m: int, k: int) -> float:
    """Compute recall@k."""
    try:
        pred = np.fromfile(pred_path, dtype=np.int64).reshape(m, k)
        gt = np.load(gt_path)
        
        recalls = []
        for i in range(m):
            pred_set = set(pred[i].tolist())
            gt_set = set(gt[i].tolist())
            recall = len(pred_set & gt_set) / k
            recalls.append(recall)
        
        return np.mean(recalls)
    except Exception as e:
        print(f"Recall computation error: {e}")
        return 0.0


def measure_memory(executable: str, base_path: str, query_path: str) -> float:
    """Measure peak memory using /usr/bin/time."""
    try:
        result = subprocess.run(
            ["/usr/bin/time", "-v", executable, base_path, query_path,
             "/tmp/memtest_output.bin", "10"],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        # Parse memory from stderr
        for line in result.stderr.split('\n'):
            if "Maximum resident set size" in line:
                kb = int(line.split()[-1])
                return kb / 1024 / 1024  # GB
        
        return 999.0
    except:
        return 999.0


def compute_score(latency: float, recall: float, memory_gb: float) -> float:
    """Compute final score."""
    # Hard constraints
    if memory_gb >= 3.0:
        return 0.0
    if latency >= 3.0:
        return 0.0
    if recall < 0.85:
        return 0.0
    
    # Score components
    lat_score = max(0, 1 - latency / 3.0)
    rec_score = min(1.0, recall / 0.95)
    mem_score = max(0, 1 - memory_gb / 6.0)
    
    return 0.5 * lat_score + 0.3 * rec_score + 0.2 * mem_score


def main():
    print("=== Kimi-k2.5 Multi-Round Vector Search Optimization Test ===")
    print(f"Max rounds: {MAX_ROUNDS}")
    print(f"Target: latency < {TARGET_LATENCY}s, recall >= {TARGET_RECALL}")
    print("")
    
    # Paths
    task_dir = Path(__file__).parent.parent
    data_dir = task_dir / "data"
    app_dir = task_dir / "app"
    
    base_random_bin = data_dir / "base_random.bin"
    base_skewed_bin = data_dir / "base_skewed.bin"
    queries_bin = data_dir / "queries.bin"
    gt_random = data_dir / "gt_random.npy"
    gt_skewed = data_dir / "gt_skewed.npy"
    
    # Load instruction
    instruction_path = task_dir / "instruction.md"
    with open(instruction_path) as f:
        instruction = f.read()
    
    # History of results
    history = []
    best_score = 0.0
    best_code = None
    
    print("Starting iteration...")
    
    for round_num in range(1, MAX_ROUNDS + 1):
        print(f"\n{'='*60}")
        print(f"Round {round_num}/{MAX_ROUNDS}")
        print(f"{'='*60}")
        
        # Build prompt
        if round_num == 1:
            prompt = f"""You are a C++ performance engineer.

{instruction}

CRITICAL REQUIREMENTS:
1. Must be C++11 compatible
2. Only standard library (<vector>, <algorithm>, <thread>, etc.)
3. NO third-party libraries (no Boost, Eigen, OpenMP)
4. Code must be readable with meaningful variable names
5. Add comments explaining key optimizations
6. NO memory leaks (use RAII)

Implement a complete search.cpp file.
Return ONLY the C++ code block.
"""
        else:
            # Feedback from previous round
            prev = history[-1]
            feedback = f"""
PREVIOUS ATTEMPT:
- Compilation: {'✓' if prev['compile_success'] else '✗'}
- Execution: {'✓' if prev['exec_success'] else '✗'}
- Latency: {prev.get('latency', 'N/A')}s (target: < {TARGET_LATENCY}s)
- Recall: {prev.get('recall', 'N/A'):.4f} (target: >= {TARGET_RECALL})
- Memory: {prev.get('memory_gb', 'N/A'):.2f} GB (limit: < 3GB)
- Score: {prev.get('score', 0.0):.4f}

ERROR DETAILS:
```
{prev.get('error', 'None')[:1000]}
```

Please fix the issues and provide an improved implementation.
Return ONLY the C++ code block.
"""
            prompt = f"""You are a C++ performance engineer.

{instruction}

{feedback}

Return ONLY the corrected C++ code block.
"""
        
        # Call API
        print(f"Calling kimi API...")
        try:
            response = call_kimi_api(prompt)
        except Exception as e:
            print(f"API call failed: {e}")
            history.append({
                "round": round_num,
                "error": str(e),
                "compile_success": False,
                "exec_success": False,
                "score": 0.0
            })
            continue
        
        # Extract code
        code = extract_code(response)
        if not code:
            print("ERROR: No code extracted from response")
            history.append({
                "round": round_num,
                "error": "No code extracted",
                "compile_success": False,
                "exec_success": False,
                "score": 0.0
            })
            continue
        
        print(f"Code extracted: {len(code)} chars")
        
        # Compile
        print(f"Compiling...")
        executable = f"/tmp/search_round_{round_num}"
        compile_ok, compile_err = compile_cpp(code, executable)
        
        if not compile_ok:
            print(f"Compilation failed:")
            print(compile_err[:500])
            history.append({
                "round": round_num,
                "code_length": len(code),
                "compile_success": False,
                "exec_success": False,
                "error": compile_err,
                "score": 0.0
            })
            continue
        
        print(f"Compilation successful ✓")
        
        # Run on random distribution
        print(f"Running on random distribution...")
        output_path = f"/tmp/output_random_{round_num}.bin"
        exec_ok, latency, exec_err = run_search(
            executable, str(base_random_bin), str(queries_bin), output_path
        )
        
        if not exec_ok:
            print(f"Execution failed: {exec_err[:200]}")
            history.append({
                "round": round_num,
                "code_length": len(code),
                "compile_success": True,
                "exec_success": False,
                "error": exec_err,
                "score": 0.0
            })
            continue
        
        print(f"Latency: {latency:.2f}s")
        
        # Measure memory
        print(f"Measuring memory...")
        memory_gb = measure_memory(executable, str(base_random_bin), str(queries_bin))
        print(f"Memory: {memory_gb:.2f} GB")
        
        # Compute recall
        print(f"Computing recall...")
        recall = compute_recall(output_path, str(gt_random), 1000, 10)
        print(f"Recall@10: {recall:.4f}")
        
        # Compute score
        score = compute_score(latency, recall, memory_gb)
        print(f"Score: {score:.4f}")
        
        # Save results
        result = {
            "round": round_num,
            "code_length": len(code),
            "compile_success": True,
            "exec_success": True,
            "latency": latency,
            "recall": recall,
            "memory_gb": memory_gb,
            "score": score
        }
        history.append(result)
        
        # Track best
        if score > best_score:
            best_score = score
            best_code = code
            print(f"✅ New best score!")
        
        # Check if target met
        if score >= 1.0:
            print(f"\n🎉 TARGET ACHIEVED in round {round_num}!")
            break
    
    # Save results
    output = {
        "task": "vector-search-optimization",
        "model": KIMI_MODEL,
        "max_rounds": MAX_ROUNDS,
        "history": history,
        "best_score": best_score
    }
    
    output_path = task_dir / "results" / "kimi_multi_round.json"
    output_path.parent.mkdir(exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    
    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"Total rounds: {len(history)}")
    print(f"Best score: {best_score:.4f}")
    print(f"Results saved to: {output_path}")
    
    # Show improvement curve
    scores = [h.get('score', 0.0) for h in history]
    if scores:
        print(f"\nScore progression:")
        for i, s in enumerate(scores, 1):
            print(f"  Round {i}: {s:.4f}")
    
    # Save best code
    if best_code:
        best_code_path = task_dir / "app" / "search_kimi_best.cpp"
        with open(best_code_path, "w") as f:
            f.write(best_code)
        print(f"\nBest code saved to: {best_code_path}")


if __name__ == "__main__":
    main()
