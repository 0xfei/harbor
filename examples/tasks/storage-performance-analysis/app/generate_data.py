#!/usr/bin/env python3
"""
Generate mock monitoring data for storage performance analysis task.
Simulates ~1 week of metrics with daily pattern of degradation around 11:00.
"""

import json
import random
import math

random.seed(42)

days = ["2025-11-17", "2025-11-18", "2025-11-19", "2025-11-20", "2025-11-21", "2025-11-22", "2025-11-23"]
hours = list(range(0, 24))

def normal_noise(base, pct=0.05):
    return base * (1 + random.uniform(-pct, pct))

def make_metrics():
    data = {"storage": {}, "clusters": {}}

    # --- Shared Storage metrics ---
    storage_metrics = []
    for day in days:
        for hour in hours:
            t = f"{day} {hour:02d}:00"
            is_problem = (hour == 11)

            # Read/Write throughput (GB/s)
            # Daily range 20-75GB/s, typically 25-45GB/s
            # 11:00 spike to 55-75GB/s  BUT some non-11:00 hours also reach 45-55GB/s
            # This breaks simple "high throughput → incident" hypothesis
            base_rw = 30 + 12 * math.sin(math.pi * hour / 12)
            # 14:00-16:00 "afternoon batch" can also push to 45-55GB/s without incident
            if hour in (14, 15, 16):
                base_rw = normal_noise(47, 0.1)
            if is_problem:
                rw = normal_noise(65, 0.08)
            else:
                rw = normal_noise(base_rw, 0.12)

            # IOPS
            base_iops = 120000 + 30000 * math.sin(math.pi * hour / 12)
            if is_problem:
                iops = int(normal_noise(310000, 0.1))
            else:
                iops = int(normal_noise(base_iops, 0.12))

            # Read/Write latency (ms)
            # Normal: 2-8ms. Problem: 15-40ms
            if is_problem:
                read_lat = normal_noise(28, 0.2)
                write_lat = normal_noise(22, 0.2)
            else:
                read_lat = normal_noise(4.5, 0.3)
                write_lat = normal_noise(3.8, 0.3)

            # Disk pressure (%)
            # Normal: 55-75%. Problem: disk stall causes apparent drop + recovery spike
            if is_problem:
                disk_pressure = normal_noise(62, 0.1)   # drops during stall
            else:
                disk_pressure = normal_noise(68, 0.1)

            # Metadata pressure (%) - KEY SIGNAL: always 80-90% daily!
            # During problem, io blocks so metadata pressure actually drops a bit
            if is_problem:
                meta_pressure = normal_noise(74, 0.05)  # drops during io stall
            else:
                # Normal: 80-90%
                meta_pressure = normal_noise(85, 0.06)

            storage_metrics.append({
                "time": t,
                "read_write_throughput_GBps": round(rw, 2),
                "iops": iops,
                "read_latency_ms": round(read_lat, 1),
                "write_latency_ms": round(write_lat, 1),
                "disk_pressure_pct": round(disk_pressure, 1),
                "metadata_pressure_pct": round(meta_pressure, 1),
            })

    data["storage"]["timeseries"] = storage_metrics

    # --- Cluster A: Main Business Cluster (the affected one) ---
    cluster_a = []
    for day in days:
        for hour in hours:
            t = f"{day} {hour:02d}:00"
            is_problem = (hour == 11)

            # Query latency P99 (seconds)
            if is_problem:
                latency_p99 = normal_noise(105, 0.25)  # 1-3 min
                latency_p50 = normal_noise(72, 0.2)
                qps = normal_noise(18, 0.2)            # qps stays or drops slightly
                scan_gb = normal_noise(8, 0.2)         # scan volume normal
            else:
                latency_p99 = normal_noise(22, 0.3)   # <30s normal
                latency_p50 = normal_noise(12, 0.25)
                qps = normal_noise(25, 0.15)
                scan_gb = normal_noise(6, 0.2)

            cluster_a.append({
                "time": t,
                "query_latency_p99_sec": round(latency_p99, 1),
                "query_latency_p50_sec": round(latency_p50, 1),
                "qps": round(qps, 1),
                "scan_volume_GBph": round(scan_gb, 2),
            })

    data["clusters"]["cluster_a_business"] = {
        "description": "Main business query cluster (most important, user-facing)",
        "timeseries": cluster_a
    }

    # --- Cluster B: The "suspect" cluster with scan spike at 11:00 ---
    # Designed to be a red herring: scan goes 10→30GB at 11:00
    # But correlation with cluster A issues is loose - on some days scan spike happens without A failing
    cluster_b = []
    for i, day in enumerate(days):
        for hour in hours:
            t = f"{day} {hour:02d}:00"
            is_scan_spike = (hour == 11)

            # Scan volume: spikes from 10GB/h to 25-35GB/h at 11
            if is_scan_spike:
                scan_gb = normal_noise(28, 0.2)
            else:
                scan_gb = normal_noise(10, 0.25)

            # QPS: relatively stable
            qps = normal_noise(40, 0.15)

            # Latency: mostly OK - this cluster is not the victim
            latency_p99 = normal_noise(15, 0.3)

            cluster_b.append({
                "time": t,
                "query_latency_p99_sec": round(latency_p99, 1),
                "qps": round(qps, 1),
                "scan_volume_GBph": round(scan_gb, 2),
            })

    data["clusters"]["cluster_b_analytics"] = {
        "description": "Analytics/batch cluster (runs scheduled jobs, 11:00 scan job)",
        "timeseries": cluster_b
    }

    # --- Cluster C: Another cluster, unaffected ---
    cluster_c = []
    for day in days:
        for hour in hours:
            t = f"{day} {hour:02d}:00"
            latency_p99 = normal_noise(18, 0.25)
            qps = normal_noise(15, 0.2)
            scan_gb = normal_noise(4, 0.3)
            cluster_c.append({
                "time": t,
                "query_latency_p99_sec": round(latency_p99, 1),
                "qps": round(qps, 1),
                "scan_volume_GBph": round(scan_gb, 2),
            })

    data["clusters"]["cluster_c_internal"] = {
        "description": "Internal tools cluster (lightweight usage)",
        "timeseries": cluster_c
    }

    # --- Disk fault events ---
    data["disk_fault_events"] = [
        {"time": "2025-11-17 11:15", "node": "storage-node-07", "action": "removed from pool, recovery 12min"},
        {"time": "2025-11-19 11:08", "node": "storage-node-12", "action": "removed from pool, recovery 9min"},
        {"time": "2025-11-21 11:22", "node": "storage-node-03", "action": "removed from pool, recovery 15min"},
        {"time": "2025-11-22 11:05", "node": "storage-node-19", "action": "removed from pool, recovery 8min"},
    ]

    # --- Incident timeline for Cluster A ---
    data["cluster_a_incidents"] = [
        {"date": "2025-11-17", "start": "10:57", "end": "12:14", "p99_peak_sec": 118, "recovery": "manually throttled qps"},
        {"date": "2025-11-18", "start": "11:02", "end": "12:30", "p99_peak_sec": 143, "recovery": "manually throttled qps + scan limit"},
        {"date": "2025-11-19", "start": "11:08", "end": "12:05", "p99_peak_sec": 97,  "recovery": "removed faulty disk + throttled qps"},
        {"date": "2025-11-20", "start": "11:01", "end": "12:44", "p99_peak_sec": 162, "recovery": "manually throttled qps"},
        {"date": "2025-11-21", "start": "10:58", "end": "11:52", "p99_peak_sec": 88,  "recovery": "removed faulty disk + throttled qps"},
        {"date": "2025-11-22", "start": "11:03", "end": "12:21", "p99_peak_sec": 131, "recovery": "manually throttled qps + scan limit"},
        {"date": "2025-11-23", "start": "11:06", "end": "12:58", "p99_peak_sec": 177, "recovery": "manually throttled qps"},
    ]

    # Additional context: days when cluster_b scan spike happened but cluster_a was NOT severely impacted
    # (breaks the simple causation hypothesis)
    data["notes"] = {
        "no_incident_but_scan_spike": [
            "2025-11-18 at 11:00 cluster_b scan was 31.2 GB/h, but cluster_a p99 only reached 26s (normal)",
            "2025-11-23 at 11:00 cluster_b scan was 27.8 GB/h, yet cluster_a p99 reached 177s",
        ],
        "storage_team_feedback": "Storage team reports this shared storage cluster is consistently running at 80-90% metadata pressure. Any spike causes cascading delays.",
        "engine_team_feedback": "Cluster A engine team reports the cluster has been running 'hot' for months, needing capacity expansion or business splitting.",
        "mitigation_works": "Each incident resolved within 10-15 min after throttling query qps/scan on Cluster A. Cluster B throttling has no effect.",
    }

    return data

if __name__ == "__main__":
    data = make_metrics()
    with open("monitoring_data.json", "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("Generated monitoring_data.json")
    print(f"Storage timeseries: {len(data['storage']['timeseries'])} data points")
    print(f"Cluster A incidents: {len(data['cluster_a_incidents'])} days")
    print(f"Disk fault events: {len(data['disk_fault_events'])}")
