"""
Multi-round iteration test for vector-search-optimization (C++ implementation).

Tests whether kimi-k2.5 can:
1. Generate working C++11 implementation in first round
2. Fix compilation errors based on compiler output
3. Optimize for latency/recall/memory constraints
"""

import json
import os
import sys
import time
import subprocess
import tempfile
import numpy as np

# Bailian API configuration
import requests


def call_kimi_api(prompt: str, model: str = "kimi-k2.5") -> str:
    """Call Bailian API for kimi-k2.5."""
    api_key = os.environ.get("BAILIAN_API_KEY")
    if not api_key:
        raise ValueError("BAILIAN_API_KEY not set")
    
    url = "https://bailian.cn-beijing.aliyuncs.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 8000
    }
    
    response = requests.post(url, headers=headers, json=payload, timeout=180)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def extract_code_block(text: str, language: str = "cpp") -> str:
    """Extract code block from markdown."""
    import re
    # Try with language spec
    pattern = f"```{language}\\n(.*?)\\n```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1)
    
    # Try without language spec
    pattern = r"```\n(.*?)\n```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1)
    
    # Try to find any code block
    pattern = r"```(?:\w+)?\n(.*?)\n```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1)
    
    return None


def compile_cpp(code: str, output_path: str) -> tuple[bool, str]:
    """
    Compile C++ code.
    
    Returns:
        (success, error_message)
    """
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
    except Exception as e:
        return False, str(e)
    finally:
        os.unlink(source_path)


def run_search(executable: str, base_path: str, query_path: str, 
               output_path: str, topk: int) -> tuple[bool, float, str]:
    """
    Run compiled search executable.
    
    Returns:
        (success, latency_seconds, error_message)
    """
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
    except Exception as e:
        return False, 0.0, str(e)


def compute_recall(pred_path: str, gt: np.ndarray, m: int, k: int) -> float:
    """Compute recall@k."""
    try:
        pred = np.fromfile(pred_path, dtype=np.int64).reshape(m, k)
        
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


def main():
    print("=== Vector Search Optimization - Kimi C++ Multi-Round Test ===\n")
    
    # Load instruction
    instruction_path = "/Users/0x01f/harbor/examples/tasks/vector-search-optimization/instruction.md"
    with open(instruction_path) as f:
        instruction = f.read()
    
    # Generate small test data
    print("Generating test data...")
    np.random.seed(42)
    n_test = 10000
    m_test = 100
    
    base_test = np.random.randn(n_test, 128).astype(np.float32)
    queries_test = np.random.randn(m_test, 128).astype(np.float32)
    
    # Compute ground truth
    gt_test = []
    for q in queries_test:
        d = ((base_test - q) ** 2).sum(axis=1)
        gt_test.append(np.argsort(d)[:10])
    gt_test = np.array(gt_test)
    
    # Save test data
    test_dir = tempfile.mkdtemp()
    base_test.tofile(f"{test_dir}/base.bin")
    queries_test.tofile(f"{test_dir}/queries.bin")
    
    results = []
    
    # Round 1: Generate initial C++ implementation
    print("\n=== Round 1: Generate C++ implementation ===")
    
    prompt = f"""You are a C++ performance engineer.

{instruction}

CRITICAL REQUIREMENTS:
1. Must be C++11 compatible (use -std=c++11)
2. Only standard library allowed (<vector>, <algorithm>, <thread>, etc.)
3. NO third-party libraries (no Boost, Eigen, OpenMP, etc.)
4. Code must be readable with meaningful variable names
5. Add comments explaining key optimizations
6. Use RAII to avoid memory leaks

Implement a complete search.cpp file with:
- load_vectors() function
- search() function with multi-threading
- main() function handling command-line arguments

Return ONLY the C++ code block.
"""
    
    response = call_kimi_api(prompt)
    code = extract_code_block(response, "cpp")
    
    if not code:
        print("ERROR: No C++ code extracted from response")
        print(f"Response preview: {response[:500]}")
        return
    
    print(f"Extracted code: {len(code)} chars")
    
    # Compile
    executable = f"{test_dir}/search"
    success, error = compile_cpp(code, executable)
    
    results.append({
        "round": 1,
        "stage": "compilation",
        "success": success,
        "error": error[:500] if error else None,
        "code_length": len(code)
    })
    
    if success:
        print("✓ Compilation successful")
        
        # Run
        output_path = f"{test_dir}/output.bin"
        success, latency, error = run_search(
            executable, f"{test_dir}/base.bin", 
            f"{test_dir}/queries.bin", output_path, 10
        )
        
        if success:
            print(f"✓ Execution successful: {latency:.3f}s")
            
            recall = compute_recall(output_path, gt_test, m_test, 10)
            print(f"  Recall@10: {recall:.4f}")
            
            results.append({
                "round": 1,
                "stage": "execution",
                "success": True,
                "latency": latency,
                "recall": recall
            })
        else:
            print(f"✗ Execution failed: {error}")
            results.append({
                "round": 1,
                "stage": "execution",
                "success": False,
                "error": error[:500]
            })
    else:
        print(f"✗ Compilation failed:\n{error}")
        
        # Round 2: Fix compilation errors
        print("\n=== Round 2: Fix compilation errors ===")
        
        feedback = f"""
COMPILATION FAILED with error:
```
{error}
```

Please fix the code and provide a corrected search.cpp implementation.
Focus on C++11 compatibility and standard library usage.
"""
        
        prompt = f"""You are a C++ performance engineer.

{instruction}

{feedback}

Return ONLY the corrected C++ code block.
"""
        
        response = call_kimi_api(prompt)
        code = extract_code_block(response, "cpp")
        
        if code:
            print(f"Extracted code: {len(code)} chars")
            
            success, error = compile_cpp(code, executable)
            
            results.append({
                "round": 2,
                "stage": "compilation",
                "success": success,
                "error": error[:500] if error else None,
                "code_length": len(code)
            })
            
            if success:
                print("✓ Round 2 compilation successful")
                
                output_path = f"{test_dir}/output_r2.bin"
                success, latency, error = run_search(
                    executable, f"{test_dir}/base.bin",
                    f"{test_dir}/queries.bin", output_path, 10
                )
                
                if success:
                    recall = compute_recall(output_path, gt_test, m_test, 10)
                    print(f"✓ Execution successful: {latency:.3f}s, Recall: {recall:.4f}")
                    
                    results.append({
                        "round": 2,
                        "stage": "execution",
                        "success": True,
                        "latency": latency,
                        "recall": recall
                    })
                else:
                    print(f"✗ Execution failed: {error}")
            else:
                print(f"✗ Round 2 compilation failed:\n{error}")
    
    # Save results
    output = {
        "task": "vector-search-optimization",
        "model": "kimi-k2.5",
        "implementation": "C++11",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "results": results
    }
    
    with open("/tmp/vector_search_cpp_multi_round.json", "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"\n=== Results saved to /tmp/vector_search_cpp_multi_round.json ===")
    
    # Summary
    successful_rounds = [r for r in results if r.get("stage") == "execution" and r.get("success")]
    
    if successful_rounds:
        best = max(successful_rounds, key=lambda x: x.get("recall", 0))
        print(f"\n✅ SUCCESS: Best Recall={best['recall']:.4f} in Round {best['round']}")
    else:
        print(f"\n❌ FAILED: No successful execution after {len(results)} attempts")


if __name__ == "__main__":
    main()
