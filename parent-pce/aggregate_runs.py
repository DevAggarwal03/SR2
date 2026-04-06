#!/usr/bin/env python3
"""
aggregate_runs.py — Aggregate Multi-Trial ADSO Experiment Results
==================================================================
Reads experiment_results.json (containing events from N trials),
classifies each reconvergence event into S1–S4, computes per-scenario
statistics (mean, std, min, max, count), and outputs a summary JSON
and formatted table.

Usage:
  python3 aggregate_runs.py --input experiments/results/experiment_results.json
  python3 aggregate_runs.py --input experiments/results/experiment_results.json --output experiments/results/aggregated_stats.json
"""

import argparse
import json
import os
import sys
import numpy as np
from collections import defaultdict


# ─────────────────────────────────────────────
#  Scenario Classification (same logic as plot_results.py)
# ─────────────────────────────────────────────

def classify_scenario(event: dict) -> str:
    """
    Classify a reconvergence event into S1-S4 based on its reasons.

    S1: Link failure — partial bandwidth drop (one ASBR down)
    S2: ASBR degradation — bandwidth drop in transit domain (B or C)
    S3: ASBR fully down — all ASBRs unreachable, 100% loss
    S4: Recovery — bandwidth/delay/loss recovery or ASBR coming back UP
    """
    reasons = event.get('reasons', [])
    reasons_str = ' '.join(reasons).lower()

    # S4: Any recovery event
    if 'recovery' in reasons_str or 'asbr_now_up' in reasons_str:
        return 'S4'

    # S3: Full ASBR down (state change to DOWN, or 100% bw drop + loss)
    if 'asbr_now_down' in reasons_str or 'asbr_state_change' in reasons_str:
        return 'S3'
    if 'bw_drop:100.0%' in reasons_str and 'loss_threshold:100.0%' in reasons_str:
        return 'S3'

    # S2: Degradation in transit domain (B or C), or smaller bw drops
    domain = event.get('domain_id', '')
    if domain in ('B', 'C') and 'bw_drop' in reasons_str:
        return 'S2'

    # S1: Link failure in domain A (partial bw drop)
    if 'bw_drop' in reasons_str or 'delay_threshold' in reasons_str or 'loss_threshold' in reasons_str:
        return 'S1'

    return 'S1'  # default


# ─────────────────────────────────────────────
#  Aggregation
# ─────────────────────────────────────────────

SCENARIO_LABELS = {
    'S1': 'S1: Link Failure',
    'S2': 'S2: ASBR Degradation',
    'S3': 'S3: ASBR Down',
    'S4': 'S4: Recovery',
}


def aggregate(events: list) -> dict:
    """
    Extract and aggregate ADSO reconvergence times per scenario.
    Returns dict with per-scenario statistics.
    """
    # Collect all ADSO reconvergence times by scenario
    scenario_times = defaultdict(list)

    for e in events:
        if e.get('event') != 'reconvergence':
            continue
        if e.get('method') != 'ADSO':
            continue

        scenario = classify_scenario(e)
        reconv_ms = e.get('adso_push_ms', e.get('reconv_ms', 0))
        scenario_times[scenario].append(reconv_ms)

    # Compute statistics
    stats = {}
    for scenario in ['S1', 'S2', 'S3', 'S4']:
        values = scenario_times.get(scenario, [])
        if not values:
            stats[scenario] = {
                'label': SCENARIO_LABELS.get(scenario, scenario),
                'n': 0,
                'mean': 0.0,
                'std': 0.0,
                'min': 0.0,
                'max': 0.0,
                'values': [],
            }
        else:
            stats[scenario] = {
                'label': SCENARIO_LABELS.get(scenario, scenario),
                'n': len(values),
                'mean': round(_mean(values), 2),
                'std': round(_std(values), 2),
                'min': round(min(values), 2),
                'max': round(max(values), 2),
                'values': [round(v, 3) for v in values],
            }

    return stats


def print_summary(stats: dict):
    """Print a formatted summary table to stdout."""
    print()
    print("=" * 78)
    print("  AGGREGATED ADSO RE-CONVERGENCE STATISTICS (post-notification pipeline)")
    print("=" * 78)
    print(f"  {'Scenario':<25} {'N':>4} {'Mean (ms)':>10} {'± Std':>8} "
          f"{'Min':>8} {'Max':>8}")
    print("-" * 78)

    for scenario in ['S1', 'S2', 'S3', 'S4']:
        s = stats.get(scenario, {})
        if s.get('n', 0) == 0:
            print(f"  {SCENARIO_LABELS.get(scenario, scenario):<25} {'—':>4}")
            continue

        print(
            f"  {s['label']:<25} {s['n']:>4} "
            f"{s['mean']:>9.2f} {s['std']:>7.2f} "
            f"{s['min']:>8.2f} {s['max']:>8.2f}"
        )

    print("=" * 78)

    # Print LaTeX-ready table row format
    print()
    print("  LaTeX table rows (paste into paper-draft.tex Table III):")
    print("  " + "-" * 70)
    for scenario in ['S1', 'S2', 'S3', 'S4']:
        s = stats.get(scenario, {})
        if s.get('n', 0) == 0:
            continue
        label_map = {
            'S1': 'S1 --- Link Failure',
            'S2': 'S2 --- ASBR Degradation',
            'S3': 'S3 --- ASBR Down',
            'S4': 'S4 --- Recovery',
        }
        latex_label = label_map.get(scenario, scenario)
        mean_str = f"{s['mean']:.1f}"
        std_str = f"{s['std']:.1f}"
        print(f"  {latex_label:<28} & ${mean_str} \\pm {std_str}$ & 403{{,}}000 & 6.6  \\\\")

    print()
    total_n = sum(s.get('n', 0) for s in stats.values())
    print(f"  Total ADSO reconvergence events: {total_n}")
    print(f"  Add footnote: N={max(s.get('n',0) for s in stats.values())} "
          f"independent trials per scenario.")
    print()


# ─────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Aggregate multi-trial ADSO experiment results'
    )
    parser.add_argument('--input', required=True,
                        help='Path to experiment_results.json')
    parser.add_argument('--output', default=None,
                        help='Path to save aggregated_stats.json (optional)')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: {args.input} not found")
        sys.exit(1)

    with open(args.input) as f:
        events = json.load(f)
    print(f"Loaded {len(events)} events from {args.input}")

    stats = aggregate(events)
    print_summary(stats)

    # Save JSON output
    output_path = args.output or os.path.join(
        os.path.dirname(args.input), 'aggregated_stats.json'
    )
    with open(output_path, 'w') as f:
        json.dump(stats, f, indent=2)
    print(f"  Saved: {output_path}")


if __name__ == '__main__':
    main()
