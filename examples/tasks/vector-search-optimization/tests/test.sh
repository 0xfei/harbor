#!/bin/bash
# Main test runner for vector search optimization
# Runs data generation, ground truth, and final evaluation

set -e

DATA_DIR="/data"
APP_DIR="/app"
TEST_DIR="/tests"
LOG_DIR="/logs/verifier"

mkdir -p $LOG_DIR

echo "=== Vector Search Optimization Test Suite ==="
echo "Timestamp: $(date)"
echo ""

# Step 1: Generate data if needed
if [ ! -f "$DATA_DIR/base_random.npy" ]; then
    echo "[Step 1/3] Generating test data..."
    python3 $DATA_DIR/generate_data.py
else
    echo "[Step 1/3] Test data exists, skipping generation"
fi

# Step 2: Generate ground truth if needed
if [ ! -f "$DATA_DIR/gt_random.npy" ]; then
    echo "[Step 2/3] Generating ground truth..."
    python3 $TEST_DIR/ground_truth.py
else
    echo "[Step 2/3] Ground truth exists, skipping generation"
fi

# Step 3: Run candidate evaluation
echo ""
echo "[Step 3/3] Running candidate evaluation..."

# Check if search.cpp exists
if [ ! -f "$APP_DIR/search.cpp" ]; then
    echo "❌ ERROR: $APP_DIR/search.cpp not found!"
    echo "Agent must create search.cpp with C++ implementation."
    
    echo "0.0" > $LOG_DIR/reward.txt
    echo "missing_file" > $LOG_DIR/error.txt
    
    echo ""
    echo "=== Final Score: 0.0 ==="
    exit 0
fi

# Compile
echo "Compiling search.cpp..."
cd $APP_DIR

COMPILE_OUTPUT=$(g++ -std=c++11 -O2 -Wall -pthread -o search search.cpp 2>&1)
COMPILE_STATUS=$?

if [ $COMPILE_STATUS -ne 0 ]; then
    echo "❌ Compilation failed:"
    echo "$COMPILE_OUTPUT"
    
    echo "0.0" > $LOG_DIR/reward.txt
    echo "compilation_error" > $LOG_DIR/error.txt
    echo "$COMPILE_OUTPUT" >> $LOG_DIR/error.txt
    
    echo ""
    echo "=== Final Score: 0.0 ==="
    exit 0
fi

echo "✓ Compilation successful"

# Check for warnings
if echo "$COMPILE_OUTPUT" | grep -q "warning:"; then
    echo "⚠ Compilation warnings detected"
    WARNING_PENALTY=0.1
else
    WARNING_PENALTY=0.0
fi

# Convert numpy to binary format
echo "Converting data to binary format..."
python3 $APP_DIR/convert.py $DATA_DIR/base_random.npy $DATA_DIR/base_random.bin
python3 $APP_DIR/convert.py $DATA_DIR/base_skewed.npy $DATA_DIR/base_skewed.bin
python3 $APP_DIR/convert.py $DATA_DIR/queries.npy $DATA_DIR/queries.bin

# Run on random distribution
echo ""
echo "=== Testing on RANDOM distribution ==="
START_TIME=$(date +%s.%N)
/usr/bin/time -v $APP_DIR/search $DATA_DIR/base_random.bin $DATA_DIR/queries.bin $DATA_DIR/out_random.bin 10 2>&1 | tee /tmp/time_random.txt
END_TIME=$(date +%s.%N)
LATENCY_RANDOM=$(echo "$END_TIME - $START_TIME" | bc)

PEAK_MEM_KB=$(grep "Maximum resident set size" /tmp/time_random.txt 2>/dev/null | awk '{print $NF}' || echo "0")
PEAK_MEM_GB=$(echo "scale=2; $PEAK_MEM_KB / 1024 / 1024" | bc)

echo "Latency: ${LATENCY_RANDOM}s"
echo "Memory: ${PEAK_MEM_GB}GB"

# Run on skewed distribution
echo ""
echo "=== Testing on SKEWED distribution ==="
START_TIME=$(date +%s.%N)
$APP_DIR/search $DATA_DIR/base_skewed.bin $DATA_DIR/queries.bin $DATA_DIR/out_skewed.bin 10
END_TIME=$(date +%s.%N)
LATENCY_SKEWED=$(echo "$END_TIME - $START_TIME" | bc)

echo "Latency: ${LATENCY_SKEWED}s"

# Compute metrics
echo ""
echo "=== Computing Metrics ==="
python3 << 'PYEOF'
import numpy as np
import json
import os

data_dir = "/data"
log_dir = "/logs/verifier"

# Load ground truth
gt_random = np.load(f"{data_dir}/gt_random.npy")
gt_skewed = np.load(f"{data_dir}/gt_skewed.npy")

# Load predictions
try:
    pred_random = np.fromfile(f"{data_dir}/out_random.bin", dtype=np.int64).reshape(1000, 10)
    pred_skewed = np.fromfile(f"{data_dir}/out_skewed.bin", dtype=np.int64).reshape(1000, 10)
except Exception as e:
    print(f"ERROR loading predictions: {e}")
    with open(f"{log_dir}/reward.txt", "w") as f:
        f.write("0.0")
    exit(0)

# Compute recall
def recall_at_k(pred, gt, k=10):
    m = pred.shape[0]
    recalls = []
    for i in range(m):
        pred_set = set(pred[i].tolist())
        gt_set = set(gt[i].tolist())
        recall = len(pred_set & gt_set) / k
        recalls.append(recall)
    return np.mean(recalls)

recall_random = recall_at_k(pred_random, gt_random)
recall_skewed = recall_at_k(pred_skewed, gt_skewed)

# Get latencies from environment (passed via shell)
import subprocess
lat_r = float(subprocess.check_output(['bash', '-c', 'echo $LATENCY_RANDOM']).decode().strip() or "0")
lat_s = float(subprocess.check_output(['bash', '-c', 'echo $LATENCY_SKEWED']).decode().strip() or "0")
mem_gb = float(subprocess.check_output(['bash', '-c', 'echo $PEAK_MEM_GB']).decode().strip() or "0")
warning_penalty = float(subprocess.check_output(['bash', '-c', 'echo $WARNING_PENALTY']).decode().strip() or "0")

print(f"Recall (Random): {recall_random:.4f}")
print(f"Recall (Skewed): {recall_skewed:.4f}")
print(f"Latency (Random): {lat_r:.3f}s")
print(f"Latency (Skewed): {lat_s:.3f}s")
print(f"Memory: {mem_gb:.2f}GB")

# Compute score
# Hard constraints
if mem_gb >= 3.0:
    print("FAIL: Memory >= 3GB")
    score = 0.0
elif lat_r >= 3.0 or lat_s >= 3.0:
    print("FAIL: Latency >= 3s")
    score = 0.0
elif recall_random < 0.85 or recall_skewed < 0.85:
    print("FAIL: Recall < 0.85")
    score = 0.0
else:
    # Score components
    lat_avg = (lat_r + lat_s) / 2
    lat_score = max(0, 1 - lat_avg / 3.0)
    rec_min = min(recall_random, recall_skewed)
    rec_score = min(1.0, rec_min / 0.95)
    mem_score = max(0, 1 - mem_gb / 6.0)
    
    score = 0.5 * lat_score + 0.3 * rec_score + 0.2 * mem_score
    score = max(0, score - warning_penalty)

print(f"\nFinal Score: {score:.4f}")

# Save
with open(f"{log_dir}/reward.txt", "w") as f:
    f.write(f"{score:.4f}")

metrics = {
    "recall_random": recall_random,
    "recall_skewed": recall_skewed,
    "latency_random": lat_r,
    "latency_skewed": lat_s,
    "memory_gb": mem_gb,
    "warning_penalty": warning_penalty,
    "score": score
}

with open(f"{log_dir}/metrics.json", "w") as f:
    json.dump(metrics, f, indent=2)

PYEOF

# Final output
echo ""
echo "=== Test Complete ==="
echo "Score: $(cat $LOG_DIR/reward.txt)"
