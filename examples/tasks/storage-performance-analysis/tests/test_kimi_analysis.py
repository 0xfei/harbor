#!/usr/bin/env python3
"""
Test script: calls Kimi-k2.5 API with the storage performance analysis task.
Sends the full monitoring data and instruction, saves response.
"""

import os
import json
import time
import sys
from pathlib import Path
import requests

TASK_DIR = Path(__file__).parent.parent
DATA_FILE = TASK_DIR / "app" / "monitoring_data.json"
INSTRUCTION_FILE = TASK_DIR / "instruction.md"
RESULTS_DIR = TASK_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

API_KEY = os.environ.get("BAILIAN_API_KEY", "")
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "kimi-k2.5"


def call_kimi_api(prompt: str, max_tokens: int = 8000) -> str:
    if not API_KEY:
        raise ValueError("BAILIAN_API_KEY not set")
    url = f"{BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are a senior infrastructure engineer specializing in distributed storage and query engine performance analysis.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=300)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def summarize_data(d: dict) -> str:
    lines = []

    lines.append("## Shared Storage Time-Series (hourly, 2025-11-17 to 2025-11-23)")
    lines.append("| Time | RW_GB/s | IOPS | ReadLat_ms | WriteLat_ms | DiskPressure% | MetaPressure% |")
    lines.append("|------|---------|------|-----------|------------|---------------|---------------|")
    for row in d["storage"]["timeseries"]:
        lines.append(
            f"| {row['time']} | {row['read_write_throughput_GBps']} | {row['iops']} "
            f"| {row['read_latency_ms']} | {row['write_latency_ms']} "
            f"| {row['disk_pressure_pct']} | {row['metadata_pressure_pct']} |"
        )

    lines.append("\n## Cluster A (Business, user-facing) Time-Series")
    lines.append("| Time | P99_sec | P50_sec | QPS | Scan_GBph |")
    lines.append("|------|---------|---------|-----|-----------|")
    for row in d["clusters"]["cluster_a_business"]["timeseries"]:
        lines.append(
            f"| {row['time']} | {row['query_latency_p99_sec']} | {row['query_latency_p50_sec']} "
            f"| {row['qps']} | {row['scan_volume_GBph']} |"
        )

    lines.append("\n## Cluster B (Analytics/Batch) Time-Series")
    lines.append("| Time | P99_sec | QPS | Scan_GBph |")
    lines.append("|------|---------|-----|-----------|")
    for row in d["clusters"]["cluster_b_analytics"]["timeseries"]:
        lines.append(
            f"| {row['time']} | {row['query_latency_p99_sec']} | {row['qps']} | {row['scan_volume_GBph']} |"
        )

    lines.append("\n## Cluster C (Internal Tools) Time-Series")
    lines.append("| Time | P99_sec | QPS | Scan_GBph |")
    lines.append("|------|---------|-----|-----------|")
    for row in d["clusters"]["cluster_c_internal"]["timeseries"]:
        lines.append(
            f"| {row['time']} | {row['query_latency_p99_sec']} | {row['qps']} | {row['scan_volume_GBph']} |"
        )

    lines.append("\n## Cluster A Incident Log")
    lines.append("| Date | Start | End | P99_Peak_sec | Recovery |")
    lines.append("|------|-------|-----|-------------|---------|")
    for inc in d["cluster_a_incidents"]:
        lines.append(
            f"| {inc['date']} | {inc['start']} | {inc['end']} "
            f"| {inc['p99_peak_sec']} | {inc['recovery']} |"
        )

    lines.append("\n## Disk Fault Events")
    for ev in d["disk_fault_events"]:
        lines.append(f"- {ev['time']}: {ev['node']} — {ev['action']}")

    lines.append("\n## Team Notes / Key Observations")
    notes = d["notes"]
    lines.append(f"- Storage team: {notes['storage_team_feedback']}")
    lines.append(f"- Engine team: {notes['engine_team_feedback']}")
    lines.append(f"- Mitigation: {notes['mitigation_works']}")
    lines.append("- Observed anomalies:")
    for obs in notes["no_incident_but_scan_spike"]:
        lines.append(f"  * {obs}")

    return "\n".join(lines)


def main():
    monitoring_data = json.loads(DATA_FILE.read_text())
    instruction = INSTRUCTION_FILE.read_text()
    prompt = f"{instruction}\n\n---\n\n# Monitoring Data\n\n{summarize_data(monitoring_data)}"

    print(f"Calling {MODEL} with storage performance analysis task...")
    print(f"Prompt length: {len(prompt)} chars")
    start = time.time()
    answer = call_kimi_api(prompt)
    elapsed = time.time() - start

    print(f"Response received in {elapsed:.1f}s, {len(answer)} chars\n")

    result = {
        "model": MODEL,
        "elapsed_sec": round(elapsed, 1),
        "response_chars": len(answer),
        "answer": answer,
    }
    (RESULTS_DIR / "kimi_analysis_test.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False)
    )
    (RESULTS_DIR / "kimi_analysis_response.txt").write_text(answer)

    print("=== Kimi Response ===")
    print(answer)
    print(f"\n=== Saved to {RESULTS_DIR}/ ===")


if __name__ == "__main__":
    main()
