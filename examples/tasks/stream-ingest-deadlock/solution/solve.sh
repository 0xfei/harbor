#!/bin/bash
# solution/solve.sh — Oracle for stream-ingest-deadlock
set -e

# 创建修复后的 dispatcher.py
cat > /app/dispatcher.py <<'EOF'
import json
import threading
import queue
from dedup import Dedup
from wal import WAL

class Dispatcher:
    def __init__(self):
        self.q = queue.Queue(maxsize=256)
        self.lock = threading.Lock()
        self.wal = WAL()
        self.dedup = Dedup()
        self.done = False
        self.processed = 0
        self.order = {i: -1 for i in range(8)}

    def producer(self):
        with open("/data/events.jsonl") as f:
            for line in f:
                evt = json.loads(line)
                self.q.put(evt)  # Queue 本身线程安全，无需外层锁
        self.done = True

    def consumer(self):
        while not self.done or not self.q.empty():
            try:
                evt = self.q.get(timeout=0.1)
            except queue.Empty:
                continue
            self.commit(evt)

    def commit(self, evt):
        with self.lock:  # 只用一把锁保护共享状态
            if self.dedup.check(evt["id"]):
                s = evt["shard"]
                if evt["seq"] > self.order[s]:
                    self.order[s] = evt["seq"]
                    self.wal.append(evt["id"])
                    self.processed += 1

    def run(self):
        t1 = threading.Thread(target=self.producer)
        workers = [threading.Thread(target=self.consumer) for _ in range(4)]

        t1.start()
        for w in workers:
            w.start()

        t1.join()
        for w in workers:
            w.join()
EOF

echo "[solve] Fixed dispatcher.py written"
