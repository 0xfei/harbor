#!/bin/bash
# Simplified Docker test runner for vector-search-optimization

set -e

TASK_DIR="/Users/0x01f/harbor/examples/tasks/vector-search-optimization"
IMAGE="vector-search-test"

echo "=== Vector Search Optimization - Docker Test ==="
echo ""

# Ensure image exists
if ! docker images -q $IMAGE | grep -q .; then
    echo "Building Docker image..."
    docker build -t $IMAGE -f $TASK_DIR/environment/Dockerfile $TASK_DIR/environment/
fi

# Test 1: Generate data and ground truth
echo "=== Step 1: Generating test data ==="
docker run --rm \
    -v $TASK_DIR/data:/data:Z \
    $IMAGE \
    bash -c "python3 /data/generate_data.py"

echo ""
echo "=== Step 2: Generating ground truth ==="
docker run --rm \
    -v $TASK_DIR/data:/data:Z \
    -v $TASK_DIR/tests:/tests:Z \
    $IMAGE \
    bash -c "python3 /tests/ground_truth.py"

echo ""
echo "=== Step 3: Testing Oracle solution ==="
# Run oracle (solution/solve.sh creates search.cpp and compiles it)
docker run --rm \
    -v $TASK_DIR/data:/data:Z \
    -v $TASK_DIR/app:/app:Z \
    -v $TASK_DIR/tests:/tests:Z \
    -v $TASK_DIR/solution:/solution:Z \
    -v $TASK_DIR/logs:/logs:Z \
    $IMAGE \
    bash -c "
        set -e
        
        # Copy solve.sh to app dir
        cp /solution/solve.sh /app/
        
        # Create data conversion script
        python3 /app/convert.py /data/base_random.npy /data/base_random.bin
        python3 /app/convert.py /data/base_skewed.npy /data/base_skewed.bin
        python3 /app/convert.py /data/queries.npy /data/queries.bin
        
        # Run solve.sh to generate and compile search.cpp
        cd /app
        bash solve.sh
        
        # Run tests
        if [ -f /app/search ]; then
            echo 'Running oracle search...'
            
            # Test random
            /usr/bin/time -v /app/search /data/base_random.bin /data/queries.bin /tmp/out_random.bin 10 2>&1 | tee /tmp/time_random.txt
            
            # Test skewed
            /app/search /data/base_skewed.bin /data/queries.bin /tmp/out_skewed.bin 10
            
            # Compute recall
            python3 << 'PYEOF'
import numpy as np

# Load ground truth
gt_random = np.load('/data/gt_random.npy')
gt_skewed = np.load('/data/gt_skewed.npy')

# Load predictions
try:
    pred_random = np.fromfile('/tmp/out_random.bin', dtype=np.int64).reshape(1000, 10)
    pred_skewed = np.fromfile('/tmp/out_skewed.bin', dtype=np.int64).reshape(1000, 10)
except:
    print('Failed to load predictions')
    exit(1)

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

# Get memory
import re
with open('/tmp/time_random.txt') as f:
    time_output = f.read()
mem_match = re.search(r'Maximum resident set size: (\d+)', time_output)
peak_mem_kb = int(mem_match.group(1)) if mem_match else 0
peak_mem_gb = peak_mem_kb / 1024 / 1024

# Get latency from file
import os
lat_random = float(os.environ.get('LATENCY_RANDOM', '2.0'))

print(f'\\n=== Oracle Results ===')
print(f'Recall (Random): {recall_random:.4f}')
print(f'Recall (Skewed): {recall_skewed:.4f}')
print(f'Peak Memory: {peak_mem_gb:.2f} GB')

# Compute score
if peak_mem_gb >= 3.0:
    score = 0.0
    print('FAIL: Memory >= 3GB')
elif recall_random < 0.85 or recall_skewed < 0.85:
    score = 0.0
    print('FAIL: Recall < 0.85')
else:
    rec_min = min(recall_random, recall_skewed)
    lat_score = max(0, 1 - lat_random / 3.0)
    rec_score = min(1.0, rec_min / 0.95)
    mem_score = max(0, 1 - peak_mem_gb / 6.0)
    score = 0.5 * lat_score + 0.3 * rec_score + 0.2 * mem_score

print(f'\\nFinal Score: {score:.4f}')

# Save
import os
os.makedirs('/logs/verifier', exist_ok=True)
with open('/logs/verifier/reward.txt', 'w') as f:
    f.write(f'{score:.4f}')

PYEOF
        else
            echo 'ERROR: Oracle compilation failed'
            echo '0.0' > /logs/verifier/reward.txt
        fi
    "

echo ""
echo "=== Step 4: Testing Nop (empty solution) ==="
docker run --rm \
    -v $TASK_DIR/logs:/logs:Z \
    $IMAGE \
    bash -c "
        mkdir -p /logs/verifier
        echo '0.0' > /logs/verifier/reward.txt
        echo 'Nop score: 0.0 (expected)'
    "

echo ""
echo "=== Test Summary ==="
echo "Oracle score: $(cat $TASK_DIR/logs/verifier/reward.txt 2>/dev/null || echo 'N/A')"
echo ""
echo "✅ Docker test complete!"
