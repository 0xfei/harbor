#!/bin/bash
# Manual test script for distributed-chaos-system

echo "=== Building test container ==="
docker build -t distributed-test:latest -f /Users/0x01f/harbor/examples/tasks/distributed-chaos-system/environment/Dockerfile /Users/0x01f/harbor/examples/tasks/distributed-chaos-system/environment/ 2>&1 | tail -3

echo ""
echo "=== Testing nop baseline (should be non-deterministic) ==="
docker run --rm -v /Users/0x01f/harbor/examples/tasks/distributed-chaos-system/tests:/tests -v /Users/0x01f/harbor/examples/tasks/distributed-chaos-system/app:/app -v /Users/0x01f/harbor/examples/tasks/distributed-chaos-system/data:/data distributed-test:latest bash -c '
cd /app
echo "Run 1:"
python3 main.py 2>&1 && cat /tmp/result.json
echo ""
echo "Run 2:"
python3 main.py 2>&1 && cat /tmp/result.json
echo ""
echo "Run 3:"
python3 main.py 2>&1 && cat /tmp/result.json
'

echo ""
echo "=== Testing oracle fix ==="
docker run --rm -v /Users/0x01f/harbor/examples/tasks/distributed-chaos-system/tests:/tests -v /Users/0x01f/harbor/examples/tasks/distributed-chaos-system/app:/app -v /Users/0x01f/harbor/examples/tasks/distributed-chaos-system/data:/data -v /Users/0x01f/harbor/examples/tasks/distributed-chaos-system/solution:/solution distributed-test:latest bash -c '
cd /app
bash /solution/solve.sh
echo ""
echo "After fix - Run 1:"
python3 main.py && cat /tmp/result.json
echo ""
echo "After fix - Run 2:"
python3 main.py && cat /tmp/result.json
echo ""
echo "After fix - Run 3:"
python3 main.py && cat /tmp/result.json
'
