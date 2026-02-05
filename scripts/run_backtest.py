#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import importlib
from pathlib import Path
from typing import Dict

import pandas as pd

from backtest import BacktestOrchestrator
from backtest.orchestrator import STRATEGY_MAP
from configs.loader import load_config
from data.io import (
    load_ohlc_csv,
    merge_h1_to_m15,
    merge_h1_to_m15_with_atr,
    merge_h4_to_m15,
    prepare_h1_features,
    prepare_h1_features_with_atr,
    prepare_h4_features,
)


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
    # M15 execution data
    parser.add_argument("--eurusd", help="Path to EURUSD OHLC CSV (M15 execution).")
    parser.add_argument("--gbpusd", help="Path to GBPUSD OHLC CSV.")
    parser.add_argument("--usdjpy", help="Path to USDJPY OHLC CSV.")
    
    # H1 trend filter data (optional)
    parser.add_argument("--eurusd_h1", help="Path to EURUSD H1 CSV (optional trend filter).")
    parser.add_argument("--gbpusd_h1", help="Path to GBPUSD H1 CSV (optional trend filter).")
    parser.add_argument("--usdjpy_h1", help="Path to USDJPY H1 CSV (optional trend filter).")
    
    # H4 bias data (optional for S7)
    parser.add_argument("--eurusd_h4", help="Path to EURUSD H4 CSV (optional for S7 HTF bias).")
    parser.add_argument("--gbpusd_h4", help="Path to GBPUSD H4 CSV (optional for S7 HTF bias).")
    parser.add_argument("--usdjpy_h4", help="Path to USDJPY H4 CSV (optional for S7 HTF bias).")
    
    parser.add_argument("--out", default="runs/", help="Output directory for results.")
    args = parser.parse_args()

    if not any([args.eurusd, args.gbpusd, args.usdjpy]):
        parser.error("At least one symbol path must be provided.")

    return args


def _load_symbols(args: argparse.Namespace, cfg) -> Dict[str, pd.DataFrame]:
    """Load M15 data and optionally merge H1/H4 features using config-driven parameters."""
    df_by_symbol: Dict[str, pd.DataFrame] = {}
    mapping = {
        "EURUSD": (args.eurusd, args.eurusd_h1, args.eurusd_h4),
        "GBPUSD": (args.gbpusd, args.gbpusd_h1, args.gbpusd_h4),
        "USDJPY": (args.usdjpy, args.usdjpy_h1, args.usdjpy_h4),
    }
    
    # Check which strategies are enabled and what they require
    h1_needed = False
    h4_needed = False
    h1_params = {}
    h4_params = {}
    
    for strategy_id in cfg.strategies.enabled:
        try:
            module_path = STRATEGY_MAP.get(strategy_id)
            if module_path:
                module = importlib.import_module(module_path)
                if hasattr(module, "required_features"):
                    required_features = module.required_features()
                    
                    # Check for H1 requirement
                    if any(feat in required_features for feat in ["trend_bias_h1", "atr_h1", "atr_h1_pips"]):
                        h1_needed = True
                        strategy_params = cfg.strategies.params.get(strategy_id, {})
                        h1_params = {
                            "ema_fast": int(strategy_params.get("ema_fast_h1", 50)),
                            "ema_slow": int(strategy_params.get("ema_slow_h1", 200)),
                            "adx_th": float(strategy_params.get("adx_th_h1", 20.0)),
                            "adx_period": int(strategy_params.get("adx_period_h1", 14)),
                            "atr_period": int(strategy_params.get("atr_period_h1", 14)),
                        }
                    
                    # Check for H4 requirement
                    if any(feat in required_features for feat in ["trend_bias_h4", "ema_fast_h4", "ema_slow_h4", "adx_h4"]):
                        h4_needed = True
                        strategy_params = cfg.strategies.params.get(strategy_id, {})
                        h4_params = {
                            "ema_fast": int(strategy_params.get("ema_fast_h4", 50)),
                            "ema_slow": int(strategy_params.get("ema_slow_h4", 200)),
                            "adx_period": int(strategy_params.get("adx_period_h4", 14)),
                            "adx_min": float(strategy_params.get("adx_min_h4", 20.0)),
                        }
        except (ImportError, AttributeError):
            pass
    
    # Validate S7 requirements: if S7 enabled, BOTH H4 and H1 must be provided
    if "S7_HTF_TREND_LTF_PULLBACK" in cfg.strategies.enabled:
        h4_needed = True
        h1_needed = True
    
    for symbol, (path_m15, path_h1, path_h4) in mapping.items():
        if path_m15:
            df_m15 = load_ohlc_csv(path_m15)
            
            # Merge H4 features if needed
            if h4_needed:
                if not path_h4:
                    raise ValueError(
                        f"Strategy S7_HTF_TREND_LTF_PULLBACK requires --{symbol.lower()}_h4 to be provided"
                    )
                df_h4 = load_ohlc_csv(path_h4)
                df_h4 = prepare_h4_features(
                    df_h4,
                    symbol=symbol,
                    ema_fast=h4_params["ema_fast"],
                    ema_slow=h4_params["ema_slow"],
                    adx_period=h4_params["adx_period"],
                    adx_min=h4_params["adx_min"],
                )
                df_m15 = merge_h4_to_m15(df_m15, df_h4)
            
            # Merge H1 features if needed
            if h1_needed:
                if not path_h1:
                    raise ValueError(
                        f"Strategy S7_HTF_TREND_LTF_PULLBACK requires --{symbol.lower()}_h1 to be provided"
                    )
                df_h1 = load_ohlc_csv(path_h1)
                df_h1 = prepare_h1_features_with_atr(
                    df_h1,
                    symbol=symbol,
                    ema_fast=h1_params["ema_fast"],
                    ema_slow=h1_params["ema_slow"],
                    adx_th=h1_params["adx_th"],
                    adx_period=h1_params["adx_period"],
                    atr_period=h1_params["atr_period"],
                )
                df_m15 = merge_h1_to_m15_with_atr(df_m15, df_h1)
                
                # Validate
                if "atr_h1_pips" not in df_m15.columns:
                    raise ValueError(f"After H1 merge for {symbol}: 'atr_h1_pips' column missing!")
                if df_m15["atr_h1_pips"].isna().all():
                    print(f"WARNING: {symbol}: 'atr_h1_pips' is all-NaN after merge. H1 data may be misaligned.")
            
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
    df_by_symbol = _load_symbols(args, cfg)

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
