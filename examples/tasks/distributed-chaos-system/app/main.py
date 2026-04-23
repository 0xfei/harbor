import json
import os

def run():
    # 确保工作目录正确
    os.chdir("/app")
    
    from billing import Billing
    from wal import WAL
    from cache import Cache
    from ledger import Ledger

    wal = WAL()
    cache = Cache()
    ledger = Ledger()
    billing = Billing(wal, cache, ledger)

    with open("/data/events.jsonl") as f:
        for i, line in enumerate(f):
            e = json.loads(line)
            billing.process(e, shard=i % 3)

    result = {
        "ledger_size": len(ledger.records),
        "replay_size": len(wal.log),
        "users": len(set(x[0] for x in ledger.records))
    }

    with open("/tmp/result.json", "w") as f:
        json.dump(result, f)

if __name__ == "__main__":
    run()
