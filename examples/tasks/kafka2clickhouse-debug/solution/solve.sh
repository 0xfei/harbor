#!/bin/bash
# Solution: Fix the Kafka rebalance batching issue

# The bug is in ReadBufferFromKafkaConsumer.cpp
# After rebalance, waited_for_assignment is reset to 0 (line 75)
# This causes poll() to use long timeout (500ms) instead of short timeout (50ms)
# Long timeout hurts batching efficiency and causes small files

# The fix is to reset waited_for_assignment AFTER successfully polling messages
# This ensures we go back to short timeout for better batching

# File: ReadBufferFromKafkaConsumer.cpp
# Line: Before line 395 (messages = std::move(new_messages);)

# Add this line:
# waited_for_assignment = 0;

# Full context:
# Line 393: else
# Line 394: {
# Line 395:     waited_for_assignment = 0;  # <-- ADD THIS LINE
# Line 396:     messages = std::move(new_messages);
# Line 397:     current = messages.begin();
# ...
# Line 400: }

# Explanation:
# 1. Rebalance sets waited_for_assignment = 0 (line 75)
# 2. First successful poll after rebalance increments it to 500 (line 373)
# 3. Without reset, it stays > 15000, using long timeout forever
# 4. Adding reset after successful poll restores short timeout behavior
# 5. Short timeout (50ms) improves batching and reduces small files

# Apply the fix
sed -i '394a\            waited_for_assignment = 0;' ReadBufferFromKafkaConsumer.cpp

echo "Fix applied successfully"
echo "Added: waited_for_assignment = 0; before line 395"
