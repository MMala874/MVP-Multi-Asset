#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict

import pandas as pd

from backtest import BacktestOrchestrator
from configs.loader import load_config
from data.io import load_ohlc_csv, merge_h1_to_m15, prepare_h1_features


_DEFAULT_METRICS = {
    "trades": 0.0,
    "expectancy": 0.0,
    "profit_factor": 0.0,
    "max_drawdown": 0.0,
    "cvar_95": 0.0,
    "max_win_streak": 0.0,
    "max_loss_streak": 0.0,
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a clean backtest from CLI.")
    parser.add_argument(
        "--config",
        default="configs/examples/example_config.yaml",
        help="Path to the YAML config file.",
    )
    parser.add_argument("--eurusd", help="Path to EURUSD OHLC CSV (M15 execution).")
    parser.add_argument("--eurusd_h1", help="Path to EURUSD H1 CSV (optional trend filter).")
    parser.add_argument("--gbpusd", help="Path to GBPUSD OHLC CSV.")
    parser.add_argument("--gbpusd_h1", help="Path to GBPUSD H1 CSV (optional trend filter).")
    parser.add_argument("--usdjpy", help="Path to USDJPY OHLC CSV.")
    parser.add_argument("--usdjpy_h1", help="Path to USDJPY H1 CSV (optional trend filter).")
    parser.add_argument("--out", default="runs/", help="Output directory for results.")
    args = parser.parse_args()

    if not any([args.eurusd, args.gbpusd, args.usdjpy]):
        parser.error("At least one symbol path must be provided.")

    return args


def _load_symbols(args: argparse.Namespace) -> Dict[str, pd.DataFrame]:
    df_by_symbol: Dict[str, pd.DataFrame] = {}
    mapping = {
        "EURUSD": (args.eurusd, args.eurusd_h1),
        "GBPUSD": (args.gbpusd, args.gbpusd_h1),
        "USDJPY": (args.usdjpy, args.usdjpy_h1),
    }
    for symbol, (path_m15, path_h1) in mapping.items():
        if path_m15:
            df_m15 = load_ohlc_csv(path_m15)
            # Optionally merge H1 filter
            if path_h1:
                df_h1 = load_ohlc_csv(path_h1)
                # Prepare H1 features before merge
                # Default params: ema_fast=8, ema_slow=21, adx_th=25.0, adx_period=14
                df_h1 = prepare_h1_features(df_h1, ema_fast=8, ema_slow=21, adx_th=25.0, adx_period=14)
                df_m15 = merge_h1_to_m15(df_m15, df_h1)
            df_by_symbol[symbol] = df_m15
    return df_by_symbol


def _print_summary(trades: pd.DataFrame, report: Dict[str, object]) -> None:
    print(f"Trades: {len(trades)}")
    scenario_metrics = report.get("metrics", {}).get("by_scenario", {})
    for scenario in ["A", "B", "C"]:
        metrics = scenario_metrics.get(scenario, _DEFAULT_METRICS)
        print(f"Scenario {scenario}: {metrics}")


def main() -> None:
    args = _parse_args()
    cfg = load_config(args.config)
    df_by_symbol = _load_symbols(args)

    orchestrator = BacktestOrchestrator()
    trades, report = orchestrator.run(df_by_symbol, cfg)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    trades_path = out_dir / "trades.csv"
    report_path = out_dir / "report.json"

    trades_output = trades.reindex(sorted(trades.columns), axis=1)
    trades_output.to_csv(trades_path, index=False)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    _print_summary(trades, report)


if __name__ == "__main__":
    main()
