#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict

import pandas as pd

from configs.loader import load_config
from data.io import load_ohlc_csv
from validation.filter_tuner import FilterTuner


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run parameter tuning from CLI.")
    parser.add_argument(
        "--config",
        default="configs/examples/example_config.yaml",
        help="Path to the YAML config file.",
    )
    parser.add_argument(
        "--strategy_id",
        default="S1_TREND_EMA_ATR_ADX",
        help="Strategy ID to tune.",
    )
    parser.add_argument("--eurusd", help="Path to EURUSD OHLC CSV.")
    parser.add_argument("--gbpusd", help="Path to GBPUSD OHLC CSV.")
    parser.add_argument("--usdjpy", help="Path to USDJPY OHLC CSV.")
    parser.add_argument("--out", default="runs_tuning/", help="Output directory for results.")
    parser.add_argument("--top_k", type=int, default=10, help="Number of top results to save.")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        default=True,
        help="Overwrite output files if they exist.",
    )
    args = parser.parse_args()

    if not any([args.eurusd, args.gbpusd, args.usdjpy]):
        parser.error("At least one symbol path must be provided.")

    return args


def _load_symbols(args: argparse.Namespace) -> Dict[str, pd.DataFrame]:
    df_by_symbol: Dict[str, pd.DataFrame] = {}
    mapping = {
        "EURUSD": args.eurusd,
        "GBPUSD": args.gbpusd,
        "USDJPY": args.usdjpy,
    }
    for symbol, path in mapping.items():
        if path:
            df_by_symbol[symbol] = load_ohlc_csv(path)
    return df_by_symbol


def main() -> None:
    args = _parse_args()
    cfg = load_config(args.config)
    df_by_symbol = _load_symbols(args)

    tuner = FilterTuner(top_k=args.top_k)
    results = tuner.tune(args.strategy_id, cfg, df_by_symbol)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save all results
    all_results_path = out_dir / "tuning_results.json"
    all_results_csv_path = out_dir / "tuning_results.csv"

    with open(all_results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # Convert all results to CSV
    csv_data = []
    for idx, result in enumerate(results, 1):
        row = {"rank": idx, "robust_score": result["score"]}
        row.update(result["params"])
        csv_data.append(row)

    if csv_data:
        all_results_df = pd.DataFrame(csv_data)
        all_results_df.to_csv(all_results_csv_path, index=False)

    # Save top_k
    top_k_path = out_dir / "top_k.json"
    top_k_csv_path = out_dir / "top_k.csv"

    top_k_results = results[: args.top_k]
    with open(top_k_path, "w", encoding="utf-8") as f:
        json.dump(top_k_results, f, indent=2)

    top_k_data = []
    for idx, result in enumerate(top_k_results, 1):
        row = {"rank": idx, "robust_score": result["score"]}
        row.update(result["params"])
        top_k_data.append(row)

    if top_k_data:
        top_k_df = pd.DataFrame(top_k_data)
        top_k_df.to_csv(top_k_csv_path, index=False)

    # Print summary
    print(f"Candidates evaluated: {len(results)}")
    if results:
        best = results[0]
        print(f"Best robust_score: {best['score']:.6f}")
        print(f"Best params: {best['params']}")
    print(f"Outputs saved to: {out_dir.resolve()}")


if __name__ == "__main__":
    main()
