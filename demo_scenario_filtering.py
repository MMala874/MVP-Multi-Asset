#!/usr/bin/env python3
"""Demo: Scenario filtering in BacktestOrchestrator.

Shows how scenario filtering enables efficient two-stage tuning:
- Stage 1: Run B scenario only (fast) on all grid candidates
- Stage 2: Run A/B/C scenarios on top_k candidates
"""

import pandas as pd
from backtest.orchestrator import BacktestOrchestrator
from configs.loader import load_config
from data.fx import generate_synthetic_ohlc

# Create realistic synthetic data
print("Generating 1000-bar synthetic EURUSD data...")
df = generate_synthetic_ohlc(n_bars=1000, volatility=0.001, trend=0.0001)

# Load config
print("Loading config...")
cfg = load_config("configs/examples/example_config.yaml")

orchestrator = BacktestOrchestrator()

print("\n" + "="*60)
print("DEMO: Scenario Filtering")
print("="*60)

# Stage 1: Fast B-only evaluation
print("\n[STAGE 1] Fast B-only grid search (1152 combos)")
print("-" * 60)
trades_b, report_b = orchestrator.run({"EURUSD": df}, cfg, scenarios=["B"])
by_scenario_b = report_b["metrics"]["by_scenario"]
print(f"Scenarios evaluated: {list(by_scenario_b.keys())}")
print(f"  - Only 'B' evaluated: {list(by_scenario_b.keys()) == ['B']}")
print(f"  - Trades generated: {len(trades_b)}")
if "B" in by_scenario_b:
    print(f"  - Profit Factor (B): {by_scenario_b['B'].get('profit_factor', 'N/A'):.2f}")

# Stage 2: Full A/B/C evaluation on top_k
print("\n[STAGE 2] Full A/B/C evaluation on top_k (e.g., 50 combos)")
print("-" * 60)
trades_abc, report_abc = orchestrator.run({"EURUSD": df}, cfg, scenarios=["A", "B", "C"])
by_scenario_abc = report_abc["metrics"]["by_scenario"]
print(f"Scenarios evaluated: {sorted(by_scenario_abc.keys())}")
print(f"  - All 3 scenarios: {sorted(by_scenario_abc.keys()) == ['A', 'B', 'C']}")
print(f"  - Trades generated: {len(trades_abc)}")
for scenario in ["A", "B", "C"]:
    if scenario in by_scenario_abc:
        pf = by_scenario_abc[scenario].get("profit_factor", "N/A")
        print(f"  - Profit Factor ({scenario}): {pf if isinstance(pf, str) else f'{pf:.2f}'}")

# Comparison
print("\n" + "="*60)
print("EFFICIENCY IMPROVEMENT")
print("="*60)
print("\nTraditional approach (all combos get A/B/C):")
print(f"  - 1152 combos × 3 scenarios = 3,456 backtest runs")
print("\nFast & Serious approach:")
print(f"  - Stage 1: 1152 combos × 1 scenario = 1,152 runs (3x faster!)")
print(f"  - Stage 2: 50 top_k × 3 scenarios = 150 runs")
print(f"  - Total: 1,302 runs (62% reduction)")
print(f"  - Time saved: 2,154 backtest runs!")

print("\n✓ Scenario filtering enables efficient two-stage tuning")
