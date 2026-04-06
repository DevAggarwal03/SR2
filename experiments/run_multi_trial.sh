#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
#  run_multi_trial.sh — Automated Multi-Trial ADSO Experiment Runner
# ═══════════════════════════════════════════════════════════════════
#
#  Runs N iterations of all 4 failure scenarios (S1–S4) from inside
#  the Mininet CLI. After each trial, copies the experiment_results.json
#  to a timestamped backup for traceability.
#
#  Usage (from Mininet CLI):
#    mininet> sh bash experiments/run_multi_trial.sh 10
#
#  Or from a host terminal that can talk to Mininet nodes via
#  network namespaces:
#    sudo bash experiments/run_multi_trial.sh 10
#
#  Prerequisites:
#    - Mininet topology is running (topology/3dTopology.py)
#    - Parent PCE is running (parent_pce_server.py --baselines)
#    - Child PCEs for domains A, B, C are running
#
#  The script waits WAIT_S seconds between each scenario injection
#  to ensure the Child PCE poll cycle (~4s) detects the change.
# ═══════════════════════════════════════════════════════════════════

set -e

# ── Configuration ─────────────────────────────────────────────────
N_TRIALS=${1:-5}                          # Number of iterations
WAIT_S=${2:-8}                            # Wait between scenarios (2x poll interval)
RESULTS_DIR="experiments/results"         # Where experiment_results.json lives
RESULTS_FILE="${RESULTS_DIR}/experiment_results.json"

echo "═══════════════════════════════════════════════════════════════"
echo "  ADSO Multi-Trial Runner"
echo "  Trials: ${N_TRIALS}    Wait between scenarios: ${WAIT_S}s"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Ensure results directory exists
mkdir -p "${RESULTS_DIR}"

for trial in $(seq 1 ${N_TRIALS}); do
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  TRIAL ${trial} of ${N_TRIALS}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # ── Step 0: Reset — Ensure all interfaces are UP ──────────────
    echo "  [RESET] Bringing all interfaces UP..."
    ip netns exec a_asbr1 ip link set a_asbr1-eth1 up 2>/dev/null || true
    ip netns exec a_asbr2 ip link set a_asbr2-eth1 up 2>/dev/null || true
    ip netns exec b_asbr3 ip link set b_asbr3-eth1 up 2>/dev/null || true
    echo "  [RESET] Waiting ${WAIT_S}s for BGP to stabilise..."
    sleep ${WAIT_S}

    # ── S1: Link failure in Domain A (partial BW drop) ────────────
    echo "  [S1] Injecting link failure: a_asbr1-eth1 DOWN"
    ip netns exec a_asbr1 ip link set a_asbr1-eth1 down
    echo "  [S1] Waiting ${WAIT_S}s for detection..."
    sleep ${WAIT_S}

    # ── S4a: Recovery from S1 ─────────────────────────────────────
    echo "  [S4a] Recovery: a_asbr1-eth1 UP"
    ip netns exec a_asbr1 ip link set a_asbr1-eth1 up
    echo "  [S4a] Waiting ${WAIT_S}s for recovery detection..."
    sleep ${WAIT_S}

    # ── S2: ASBR degradation in Domain B ──────────────────────────
    echo "  [S2] Injecting ASBR degradation: b_asbr3-eth1 DOWN"
    ip netns exec b_asbr3 ip link set b_asbr3-eth1 down
    echo "  [S2] Waiting ${WAIT_S}s for detection..."
    sleep ${WAIT_S}

    # ── S4b: Recovery from S2 ─────────────────────────────────────
    echo "  [S4b] Recovery: b_asbr3-eth1 UP"
    ip netns exec b_asbr3 ip link set b_asbr3-eth1 up
    echo "  [S4b] Waiting ${WAIT_S}s for recovery detection..."
    sleep ${WAIT_S}

    # ── S3: Complete ASBR failure in Domain A ─────────────────────
    echo "  [S3] Injecting full ASBR failure: a_asbr1-eth1 + a_asbr2-eth1 DOWN"
    ip netns exec a_asbr1 ip link set a_asbr1-eth1 down
    ip netns exec a_asbr2 ip link set a_asbr2-eth1 down
    echo "  [S3] Waiting ${WAIT_S}s for detection..."
    sleep ${WAIT_S}

    # ── S4c: Recovery from S3 ─────────────────────────────────────
    echo "  [S4c] Recovery: a_asbr1-eth1 + a_asbr2-eth1 UP"
    ip netns exec a_asbr1 ip link set a_asbr1-eth1 up
    ip netns exec a_asbr2 ip link set a_asbr2-eth1 up
    echo "  [S4c] Waiting ${WAIT_S}s for recovery detection..."
    sleep ${WAIT_S}

    echo "  ✓ Trial ${trial} complete."
done

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ALL ${N_TRIALS} TRIALS COMPLETE"
echo ""
echo "  Next steps:"
echo "    1. Ctrl+C on the Parent PCE server to save results"
echo "    2. The final experiment_results.json contains all events"
echo "    3. Run: python3 parent-pce/aggregate_runs.py \\"
echo "         --input experiments/results/experiment_results.json"
echo "    4. Run: python3 parent-pce/plot_results.py \\"
echo "         --input experiments/results/experiment_results.json \\"
echo "         --output paper/figures/"
echo "═══════════════════════════════════════════════════════════════"
