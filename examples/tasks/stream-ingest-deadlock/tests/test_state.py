import subprocess
import time
import psutil
import json
import os

def test_all():
    os.chdir("/app")
    p = subprocess.Popen(
        ["python3", "main.py"],
        cwd="/app"
    )

    peak = 0
    start = time.time()

    while p.poll() is None:
        try:
            rss = psutil.Process(p.pid).memory_info().rss
            peak = max(peak, rss)
        except:
            pass
        time.sleep(0.05)

    dur = time.time() - start

    assert p.returncode == 0, f"Process exited with code {p.returncode}"
    assert dur < 15, f"Runtime {dur:.1f}s exceeds 15s limit"
    assert peak < 500 * 1024 * 1024, f"Peak RSS {peak/1024/1024:.1f}MB exceeds 500MB"

    with open("/tmp/result.json") as f:
        r = json.load(f)

    assert r["processed"] == 100000, f"Processed {r['processed']} != 100000"
    assert r["duplicates"] == 0, f"Found {r['duplicates']} duplicates"
