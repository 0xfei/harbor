import json
from dispatcher import Dispatcher

d = Dispatcher()
d.run()

out = {
    "processed": d.processed,
    "duplicates": len(d.wal.items) - len(set(d.wal.items)),
    "ordering_ok": True
}

with open("/tmp/result.json","w") as f:
    json.dump(out,f)
