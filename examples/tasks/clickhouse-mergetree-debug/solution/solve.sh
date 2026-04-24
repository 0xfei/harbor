#!/bin/bash
# Solution: Fix the ClickHouse MergeTree partition crash

# The bug is in MergeTreePartition.cpp line 182
# The condition only checks if key_size == 0, but doesn't check if value is empty
# When key_size > 0 but value is empty, it tries to access value[0] and crashes

# Fix: Change line 182 from:
#   if (key_size == 0)
# To:
#   if (key_size == 0 || value.empty())

# File: MergeTreePartition.cpp
# Line: 182

# Before:
#     if (key_size == 0)
# 
# After:
#     if (key_size == 0 || value.empty())

# Apply the fix using sed
sed -i '182s/if (key_size == 0)/if (key_size == 0 || value.empty())/' MergeTreePartition.cpp

echo "Fix applied successfully"
echo "Changed: if (key_size == 0)"
echo "To: if (key_size == 0 || value.empty())"
