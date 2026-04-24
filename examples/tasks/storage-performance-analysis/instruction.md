# Storage Performance Incident Analysis

## Background

You are a senior infrastructure engineer on-call. Over the past week (2025-11-17 ~ 2025-11-23),
the most important user-facing business cluster (**cluster_a_business**) has experienced daily
query latency spikes around 11:00 every morning.

- **Normal behavior**: P99 query latency < 30 seconds
- **Incident behavior**: P99 query latency 60~180 seconds (up to 3 minutes)
- **Recovery method**: Manually throttling Cluster A's QPS and scan volume limits on the
  compute engine brings P99 back to normal within 10–15 minutes

Multiple teams have escalated:
- **Storage team**: "This shared storage cluster has been running hot. Metadata pressure is
  consistently at 80–90% daily."
- **Cluster A engine team**: "We've been telling management this cluster needs capacity
  expansion or workload splitting for months."

---

## Monitoring Data

Full time-series monitoring data is available in `app/monitoring_data.json`. The JSON contains:

### `storage.timeseries`
Per-hour metrics for the shared storage layer (serves **all** clusters):
- `read_write_throughput_GBps` — combined read+write throughput
- `iops` — storage IOPS
- `read_latency_ms` / `write_latency_ms` — P99 IO latency
- `disk_pressure_pct` — disk utilization %
- `metadata_pressure_pct` — storage metadata service pressure %

### `clusters.cluster_a_business`
Per-hour metrics for the main business cluster:
- `query_latency_p99_sec` — query P99 latency (seconds)
- `qps` — queries per second
- `scan_volume_GBph` — data scanned per hour

### `clusters.cluster_b_analytics`
Per-hour metrics for the analytics/batch cluster sharing the same storage:
- Notable: a scheduled batch job runs at 11:00, causing a scan spike from ~10 GB/h to ~28 GB/h

### `clusters.cluster_c_internal`
Internal tools cluster on the same storage, low traffic.

### `disk_fault_events`
List of individual disk node failures detected during incidents (4 events over the week).

### `cluster_a_incidents`
Incident timeline: start time, end time, peak P99, recovery action for each day.

### `notes`
Key observations from both teams, plus observations breaking naive hypotheses.

---

## Key Questions

You need to analyze all available monitoring data and answer:

### 1. Root Cause Analysis
What is the **fundamental root cause** of the daily 11:00 incidents on Cluster A?
Is it:
- (a) The throughput spike caused by Cluster B's 11:00 batch job?
- (b) The occasional disk node failures that occur during incidents?
- (c) The shared storage running at sustained high pressure, making it fragile?
- (d) A specific query pattern on Cluster A at 11:00?

Justify your answer with data from the monitoring metrics.

### 2. Why Is Throttling a Mitigation, Not a Cure?
Throttling Cluster A's QPS/scan immediately relieves the incident, but the problem recurs the
next day. What does this tell you about the nature of the root cause?

### 3. Cluster B Hypothesis
Cluster B has a clear scan spike at 11:00 (10→28 GB/h) that coincides with incidents on
Cluster A. Does the data support the hypothesis that Cluster B is causing Cluster A incidents?
Look carefully at whether this correlation is consistent.

### 4. Disk Fault Hypothesis
Disk node failures occur during 4 of the 7 incidents. In other distributed storage systems,
single-node disk failures are handled gracefully. Why does it matter differently here?

### 5. Recommended Action
Based on your analysis, what is the **correct long-term fix**?
Should the team focus on:
- Investigating and blocking Cluster B's batch jobs?
- Improving disk failure handling in the storage layer?
- Treating this as a capacity/architecture problem requiring workload isolation?

---

## Constraints

- You must base your conclusions on the actual numbers in `app/monitoring_data.json`
- Quote specific metric values to support your reasoning
- Avoid recommending a "monitor more closely" or "set up better alerting" solution as the primary answer
- The answer should identify **systemic cause** over **proximate trigger**
