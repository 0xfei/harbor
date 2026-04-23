#!/usr/bin/env bash
# solution/solve.sh — Oracle reference solution.
# Uploaded by harbor to /solution/solve.sh in the container.
# Running this produces a score of 1.0 when test.sh is run afterwards.
set -euo pipefail

echo "[solve] Generating input data..."
python3 /solution/gen_data.py

echo "[solve] Generating expected output (ground truth)..."
python3 /solution/oracle.py

echo "[solve] Compiling oracle C++ solver..."
g++ -O2 -std=c++17 -pthread \
    -o /app/aggregator \
    /solution/oracle_solver.cpp

# Copy source so test_source_exists check passes (oracle wrote a valid .cpp)
cp /solution/oracle_solver.cpp /app/aggregator.cpp

echo "[solve] Running oracle aggregator..."
/app/aggregator

echo "[solve] Oracle solution complete. /data/output.tsv written."
echo "[solve] Verifying oracle output matches expected..."
diff <(sort /data/output.tsv) <(sort /data/expected.tsv) \
    && echo "[solve] MATCH: oracle output is correct." \
    || { echo "[solve] MISMATCH: oracle output differs!"; exit 1; }
