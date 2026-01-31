#!/usr/bin/env python3
from __future__ import annotations

import argparse
from itertools import product
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from backtest.orchestrator import BacktestOrchestrator
from configs.loader import load_config
from data.io import load_ohlc_csv


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Single-strategy parameter tuning with grid search."
    )
    parser.add_argument(
        "--config",
        type=str,
        default="configs/examples/example_config.yaml",
        help="Path to YAML config file.",
    )
    parser.add_argument(
        "--strategy_id",
        type=str,
        default="S1_TREND_EMA_ATR_ADX",
        help="Strategy ID to tune (e.g., S1_TREND_EMA_ATR_ADX).",
    )
    parser.add_argument("--eurusd", type=str, help="Path to EURUSD OHLC CSV.")
    parser.add_argument("--gbpusd", type=str, help="Path to GBPUSD OHLC CSV.")
    parser.add_argument("--usdjpy", type=str, help="Path to USDJPY OHLC CSV.")

    args = parser.parse_args()

    if not any([args.eurusd, args.gbpusd, args.usdjpy]):
        parser.error("At least one symbol CSV must be provided (--eurusd, --gbpusd, --usdjpy).")

    return args


def _load_data(args: argparse.Namespace) -> Dict[str, pd.DataFrame]:
    df_by_symbol: Dict[str, pd.DataFrame] = {}
    mapping = {"EURUSD": args.eurusd, "GBPUSD": args.gbpusd, "USDJPY": args.usdjpy}
    for symbol, path in mapping.items():
        if path:
            df_by_symbol[symbol] = load_ohlc_csv(path)
    return df_by_symbol


def _build_grid(strategy_id: str) -> List[Dict[str, Any]]:
    """Build grid search space for strategy parameters."""
    if strategy_id == "S1_TREND_EMA_ATR_ADX":
        ema_fast_vals = [10, 20, 30]
        ema_slow_vals = [50, 100]
        k_sl_vals = [1.5, 2.0, 2.5]
        k_tp_vals = [1.0, 1.5, 2.0]
        adx_th_vals = [20, 25, 30]
        return [
            {
                "ema_fast": ema_fast,
                "ema_slow": ema_slow,
                "k_sl": k_sl,
                "k_tp": k_tp,
                "adx_th": adx_th,
            }
            for ema_fast, ema_slow, k_sl, k_tp, adx_th in product(
                ema_fast_vals, ema_slow_vals, k_sl_vals, k_tp_vals, adx_th_vals
            )
        ]
    else:
        raise ValueError(f"Grid not yet defined for strategy: {strategy_id}")


def _run_backtest(
    cfg: Any,
    df_by_symbol: Dict[str, pd.DataFrame],
    strategy_id: str,
    params: Dict[str, Any],
) -> Dict[str, float]:
    """Run backtest for single param set, return metrics dict."""
    import copy

    cfg_copy = copy.deepcopy(cfg)
    cfg_copy.strategies.enabled = [strategy_id]
    cfg_copy.strategies.params[strategy_id] = params

    orchestrator = BacktestOrchestrator()
    trades, report = orchestrator.run(df_by_symbol, cfg_copy)

    if trades.empty:
        return {
            "trades": 0,
            "expectancy": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
        }

    overall_metrics = report.get("metrics", {}).get("overall", {})
    return {
        "trades": int(overall_metrics.get("trades", 0)),
        "expectancy": float(overall_metrics.get("expectancy", 0.0)),
        "profit_factor": float(overall_metrics.get("profit_factor", 0.0)),
        "max_drawdown": float(overall_metrics.get("max_drawdown", 0.0)),
    }


def main() -> None:
    args = _parse_args()
    cfg = load_config(args.config)
    df_by_symbol = _load_data(args)

    grid = _build_grid(args.strategy_id)
    results: List[Dict[str, Any]] = []

    print(f"Grid size: {len(grid)} combinations")
    print(f"Running tuning for {args.strategy_id}...")

    for i, params in enumerate(grid, 1):
        metrics = _run_backtest(cfg, df_by_symbol, args.strategy_id, params)
        row = {**params, **metrics}
        results.append(row)
        if i % max(1, len(grid) // 10) == 0:
            print(f"  Progress: {i}/{len(grid)}")

    df_results = pd.DataFrame(results)
    df_results = df_results.sort_values(
        by=["expectancy", "profit_factor", "max_drawdown"],
        ascending=[False, False, True],
    )

    out_dir = Path("runs")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"tuning_{args.strategy_id}.csv"
    df_results.to_csv(out_path, index=False)

    print(f"\nTop 5 parameter sets:")
    for i, row in df_results.head(5).iterrows():
        print(f"  {i+1}: expectancy={row['expectancy']:.4f}, "
              f"profit_factor={row['profit_factor']:.2f}, "
              f"max_drawdown={row['max_drawdown']:.4f}")

    print(f"\nResults saved to: {out_path.resolve()}")


if __name__ == "__main__":
    main()
