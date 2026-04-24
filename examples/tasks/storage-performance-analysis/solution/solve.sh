#!/usr/bin/env bash
# solution/solve.sh
# This is a manual-verifier task. This script documents the expected analysis conclusions.
# A correct answer must contain ALL of the following reasoning points.

set -euo pipefail

ANSWER_FILE="${1:-}"

echo "=== Storage Performance Analysis - Expected Solution ==="
echo ""
echo "Root cause: Shared storage running at sustained 80-90% metadata pressure."
echo "Any perturbation (throughput spike, single disk failure, batch job) becomes"
echo "catastrophic because the system has NO headroom."
echo ""
echo "Key evidence points the model must identify:"
echo ""
echo "1. METADATA PRESSURE (PRIMARY SIGNAL)"
echo "   - Non-incident hours: metadata_pressure_pct avg ~85% (range 80-90%)"
echo "   - Incident hours (11:00): metadata_pressure_pct DROPS to ~74-78%"
echo "   - Paradox: pressure drops DURING incidents because IO stall freezes ops"
echo "   - This is a classic sign of a saturated system going into IO stall"
echo ""
echo "2. CLUSTER B HYPOTHESIS REFUTED"
echo "   - Cluster B scan spikes to ~28-31 GB/h every day at 11:00"
echo "   - BUT: on 2025-11-18, scan was 31.2 GB/h yet Cluster A P99 was only 26s (normal)"
echo "   - On 2025-11-23, scan was 27.8 GB/h and Cluster A P99 reached 177s (worst ever)"
echo "   - No consistent correlation → Cluster B is NOT the cause"
echo ""
echo "3. THROUGHPUT NOT THE TRIGGER"
echo "   - 11:00 throughput: 62-70 GB/s (incidents every day)"
echo "   - 14:00-16:00 throughput: 49-56 GB/s (NO incidents, same storage)"
echo "   - If throughput were the trigger, 14-16:00 should also cause incidents"
echo "   - Counter-evidence: 14-16:00 metadata pressure = 85-87% (normal high baseline)"
echo "   - Conclusion: throughput spike is a trigger only because headroom is absent"
echo ""
echo "4. DISK FAULTS ARE SYMPTOMS, NOT CAUSE"
echo "   - 3 of 7 incident days had NO disk fault → disk fault is not required to trigger"
echo "   - In a healthy storage system, single node failure is handled gracefully"
echo "   - At 80-90% metadata pressure, any node loss immediately overloads survivors"
echo "   - Disk faults make incidents longer/harder to recover, not the root cause"
echo ""
echo "5. THROTTLING IS PALLIATIVE, NOT CURATIVE"
echo "   - Throttling Cluster A reduces storage load → system recovers"
echo "   - Next day: storage pressure is back to 80-90%, problem recurs"
echo "   - This confirms: root cause is sustained overload, not a transient event"
echo ""
echo "CORRECT RECOMMENDATION:"
echo "  Split Cluster A workloads onto dedicated storage, or expand storage capacity."
echo "  Target: metadata pressure < 60% in steady state."
echo "  Short-term: enforce stricter scan/QPS quotas on Cluster A as operational gate."
echo ""
echo "INCORRECT RECOMMENDATIONS (should be rejected):"
echo "  - Blocking Cluster B batch jobs (no causal evidence)"
echo "  - Improving disk fault recovery only (3 incidents had no disk fault)"
echo "  - Adding more monitoring/alerting as the primary action"
echo ""

if [[ -n "$ANSWER_FILE" && -f "$ANSWER_FILE" ]]; then
    echo "--- Checking answer file: $ANSWER_FILE ---"
    CHECKS=(
        "metadata"
        "headroom\|capacity\|pressure"
        "cluster.b\|clusterb\|batch"
        "disk.fault\|bad.disk\|disk.failure"
        "split\|isolat\|expand"
    )
    for pattern in "${CHECKS[@]}"; do
        if grep -qi "$pattern" "$ANSWER_FILE"; then
            echo "  PASS: '$pattern'"
        else
            echo "  FAIL: '$pattern' not found in answer"
        fi
    done
fi
