#!/bin/bash
# solution/solve.sh — Oracle for distributed-chaos-system

# 修复 billing.py - 移除随机性
cat > /app/billing.py <<'EOF'
from mutation import MutationEngine
from commit_graph import CommitGraph
from replay import replay
from schema import normalize_event

class Billing:

    def __init__(self, wal, cache, ledger):
        self.wal = wal
        self.cache = cache
        self.ledger = ledger
        self.mutation = MutationEngine()
        self.commit = CommitGraph()
        self.seen = set()

    def process(self, event, shard):

        if not self.commit.commit():
            return

        event = normalize_event(event)

        factor = self.mutation.mutate_factor()
        event["amount"] *= factor

        tx_id = (event["user_id"], event["event_id"])

        if tx_id in self.seen:
            return
        self.seen.add(tx_id)

        bal = self.cache.get(event["user_id"])
        bal += event["amount"]

        self.cache.set(event["user_id"], bal)
        self.ledger.write(event["user_id"], event["amount"])
        self.wal.append(event)
EOF

# 修复 mutation.py - 总是返回 1.0
cat > /app/mutation.py <<'EOF'
class MutationEngine:
    def mutate_factor(self):
        return 1.0  # 确定性：总是返回 1.0
EOF

# 修复 commit_graph.py - 总是提交
cat > /app/commit_graph.py <<'EOF'
class CommitGraph:
    def commit(self):
        return True  # 确定性：总是成功
EOF

# 修复 replay.py - 不注入假事件
cat > /app/replay.py <<'EOF'
def replay(events):
    return events  # 确定性：直接返回，不修改
EOF

echo "[solve] Fixed all non-deterministic components"
