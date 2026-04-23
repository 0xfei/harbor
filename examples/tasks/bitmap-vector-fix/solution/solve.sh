#!/usr/bin/env bash
# solution/solve.sh — Oracle: apply fixed bitmap_manager.cpp and compile
set -euo pipefail

echo "[solve] Copying header files from /solution..."
cp /solution/bitmap.h             /app/bitmap.h
cp /solution/hash.h               /app/hash.h
cp /solution/bitmap_manager.h     /app/bitmap_manager.h

# Test file is provided by the task setup (copied by test.sh later),
# but oracle runs before verifier, so we also place it here.
# The test file should exist in solution/ as well for oracle to use.
cp /solution/bitmap_manager_test.cpp /app/bitmap_manager_test.cpp

echo "[solve] Applying fixed bitmap_manager.cpp..."
cp /solution/bitmap_manager_fixed.cpp /app/bitmap_manager.cpp

echo "[solve] Compiling..."
g++ -std=c++11 -o /app/bitmap_manager_test \
    /app/bitmap_manager_test.cpp \
    /app/bitmap_manager.cpp

echo "[solve] Running tests..."
/app/bitmap_manager_test

echo "[solve] All tests passed."
