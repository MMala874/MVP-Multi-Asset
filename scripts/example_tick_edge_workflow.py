#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
INTEGRATION EXAMPLE: Tick-level edge discovery workflow

This script shows how to:
  1. Load real MT5 tick export
  2. Run edge discovery
  3. Parse results
  4. Make trading decision

Usage:
  python scripts/example_tick_edge_workflow.py --tick_file data/EURUSD_ticks.csv
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Integration example for tick-level edge discovery"
    )
    parser.add_argument(
        "--tick_file",
        type=str,
        default="data/EURUSD_ticks.csv",
        help="Path to MT5 tick CSV export",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="outputs",
        help="Output directory",
    )
    args = parser.parse_args()

    print("\n" + "="*70)
    print("TICK-LEVEL EDGE DISCOVERY WORKFLOW")
    print("="*70)

    # Step 1: Check if tick file exists
    if not os.path.exists(args.tick_file):
        print(f"\n[!] Tick file not found: {args.tick_file}")
        print("    Please export tick data from MT5 and save to:", args.tick_file)
        print("\n    Steps:")
        print("    1. MT5 Terminal > Tools > History Center")
        print("    2. Select EURUSD, download full tick history")
        print("    3. Right-click > Export > Save as CSV")
        print("    4. Ensure columns: time, bid, ask")
        print("    5. Save to:", args.tick_file)
        sys.exit(1)

    # Step 2: Run tick_edge_scan.py
    print("\n[1] Running tick-level edge discovery...")
    print(f"    Input: {args.tick_file}")
    print(f"    Output: {args.output_dir}/")

    cmd = [
        sys.executable,
        "scripts/tick_edge_scan.py",
        "--tick_file", args.tick_file,
        "--output_dir", args.output_dir,
        "--verbose",
    ]

    try:
        result = subprocess.run(cmd, capture_output=False, check=False)
    except Exception as e:
        print(f"\n[!] Error running tick_edge_scan.py: {e}")
        sys.exit(1)

    # Step 3: Load summary
    summary_path = os.path.join(args.output_dir, "summary.json")
    if not os.path.exists(summary_path):
        print(f"\n[!] Summary file not found: {summary_path}")
        sys.exit(1)

    with open(summary_path) as f:
        summary = json.load(f)

    # Step 4: Parse decision
    print("\n" + "="*70)
    print("ANALYSIS")
    print("="*70)

    decision = summary.get("decision", {})
    status = decision.get("status", "UNKNOWN")

    print(f"\nDecision: {status}")

    if status == "GO":
        print("\n✓ Edge discovered!")
        print("  → Proceed to live backtesting with discovered parameters")
        print("\n  Recommended next steps:")
        print("  1. Extract frozen parameters from summary.json")
        print("  2. Implement entry/exit logic using thresholds")
        print("  3. Backtest on 5-year data")
        print("  4. If backtest passes (DD < 5%), proceed to paper trading")
        print("  5. Monitor for 4-12 weeks before live deployment")

    elif status == "NO-GO":
        print("\n✗ Edge not discovered")
        print("  → Effect size inconsistent across years")
        print("\n  Recommended next steps:")
        print("  1. Revisit hypothesis (compression may not be edge)")
        print("  2. Try different asset pair (GBPUSD, USDJPY, etc.)")
        print("  3. Try different compression thresholds")
        print("  4. Or move to new edge hypothesis")

    # Print details
    print("\nEffect Sizes:")
    effect_sizes = summary.get("effect_sizes", {})
    for metric, ratio in effect_sizes.items():
        direction = "↑" if ratio > 1.0 else "↓"
        change = abs((ratio - 1.0) * 100)
        print(f"  {metric}: {ratio:.3f} ({direction} {change:.1f}%)")

    print("\nStability (per year):")
    stability = summary.get("stability_per_year", {})
    for metric, yearly_data in stability.items():
        n_positive = sum(1 for item in yearly_data if item["effect_ratio"] > 1.05)
        n_total = len(yearly_data)
        consistency = (n_positive / n_total * 100) if n_total > 0 else 0
        print(f"  {metric}: {consistency:.0f}% of years positive (n={n_total})")

    print("\n" + "="*70)

    # Step 5: Save execution log
    log_path = os.path.join(args.output_dir, "workflow_log.txt")
    with open(log_path, "w") as f:
        f.write("TICK-LEVEL EDGE DISCOVERY EXECUTION LOG\n")
        f.write("="*70 + "\n\n")
        f.write(f"Tick file: {args.tick_file}\n")
        f.write(f"Status: {status}\n")
        f.write(f"Effect sizes: {effect_sizes}\n")
        f.write(f"Stability: {stability}\n")

    print(f"\nExecution log saved: {log_path}")
    print("="*70 + "\n")

    return 0 if status == "GO" else 1


if __name__ == "__main__":
    sys.exit(main())
