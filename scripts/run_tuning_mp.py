#!/usr/bin/env python3
"""Multiprocessing grid search tuning with two-stage optimization.

Two-stage approach:
  Stage 1 (Fast): Evaluate all parameter combinations for tune_scenario only (default: B)
  Stage 2 (Comprehensive): Evaluate top-K candidates with full A/B/C scenarios

This significantly reduces overall evaluation time by avoiding expensive A/B/C evaluations
for candidates that won't make the top-K cutoff.

Usage:
  python -m scripts.run_tuning_mp \\
    --eurusd data.csv \\
    --gbpusd data.csv \\
    --usdjpy data.csv \\
    --out runs_tuning/ \\
    --top_k 10

Optionally disable two-stage and run all A/B/C for all combinations:
  python -m scripts.run_tuning_mp ... --two_stage False
"""
from __future__ import annotations

import argparse
import json
import os
import time
from multiprocessing import Pool, cpu_count
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from tuning.grid import build_grid
from tuning.worker import (
    run_worker,
    run_worker_single_scenario,
    run_worker_full_scenarios,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Multiprocessing grid search tuning for single strategy."
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
        help="Strategy ID to tune.",
    )
    parser.add_argument("--eurusd", type=str, help="Path to EURUSD OHLC CSV.")
    parser.add_argument("--gbpusd", type=str, help="Path to GBPUSD OHLC CSV.")
    parser.add_argument("--usdjpy", type=str, help="Path to USDJPY OHLC CSV.")
    parser.add_argument(
        "--out", type=str, default="runs_tuning/", help="Output directory."
    )
    parser.add_argument(
        "--top_k", type=int, default=10, help="Number of top results to save."
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of workers (default: cpu_count-1, max 7).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        default=True,
        help="Overwrite output files.",
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="Random seed (from config if not set)."
    )
    parser.add_argument(
        "--progress_every",
        type=int,
        default=50,
        help="Print progress every N results.",
    )
    parser.add_argument(
        "--show_eta",
        action="store_true",
        default=True,
        help="Show estimated time of arrival.",
    )
    parser.add_argument(
        "--two_stage",
        action="store_true",
        default=True,
        help="Use two-stage tuning: fast B-only, then full A/B/C for top_k.",
    )
    parser.add_argument(
        "--tune_scenario",
        type=str,
        choices=["A", "B", "C"],
        default="B",
        help="Scenario to use for stage-1 grid search (default: B).",
    )

    args = parser.parse_args()

    if not any([args.eurusd, args.gbpusd, args.usdjpy]):
        parser.error("At least one symbol CSV required (--eurusd, --gbpusd, --usdjpy).")

    return args


def _get_worker_count() -> int:
    """Get safe worker count: cpu_count-1, capped at 7."""
    count = max(1, cpu_count() - 1)
    return min(count, 7)


def _format_time(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _print_progress(
    completed: int,
    total: int,
    elapsed: float,
    best_result: Dict[str, Any],
    show_eta: bool,
) -> None:
    """Print progress line with ETA."""
    pct = (completed / total) * 100.0 if total > 0 else 0.0

    if show_eta and completed > 0:
        avg_time = elapsed / completed
        eta_seconds = avg_time * (total - completed)
        eta_str = _format_time(eta_seconds)
    else:
        eta_str = "N/A"

    elapsed_str = _format_time(elapsed)
    best_score = best_result.get("score_B", 0.0)
    best_pf = best_result.get("pf_B", 0.0)
    best_exp = best_result.get("expectancy_B", 0.0)

    print(
        f"[tuning] {completed}/{total} ({pct:.1f}%) "
        f"elapsed={elapsed_str} eta={eta_str} "
        f"best_score={best_score:.4f} best_pf_B={best_pf:.4f} best_exp_B={best_exp:.6f}"
    )



def _flatten_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten result dict for CSV export."""
    row = {}
    params = result.get("params", {})
    row.update(params)
    for key in result:
        if key != "params":
            row[key] = result[key]
    return row


def main() -> None:
    args = _parse_args()

    df_paths = {
        "EURUSD": args.eurusd,
        "GBPUSD": args.gbpusd,
        "USDJPY": args.usdjpy,
    }

    grid = build_grid(args.strategy_id)
    print(f"Grid size: {len(grid)} combinations")

    num_workers = args.workers if args.workers else _get_worker_count()
    print(f"Using {num_workers} workers")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.two_stage:
        print(f"\n=== STAGE 1: Fast {args.tune_scenario}-only Grid Search ===")
        results_stage1 = _run_stage1_fast_search(
            args, grid, df_paths, num_workers
        )

        print(f"\n=== STAGE 2: Full A/B/C Evaluation for Top-K ===")
        results_final = _run_stage2_topk_evaluation(
            args, results_stage1, df_paths, num_workers
        )
    else:
        print(f"\n=== Single Stage: Full A/B/C for all combinations ===")
        results_final = _run_single_stage(
            args, grid, df_paths, num_workers
        )

    _save_results(results_final, args, out_dir)


def _run_stage1_fast_search(
    args: argparse.Namespace,
    grid: List[Dict[str, Any]],
    df_paths: Dict[str, str],
    num_workers: int,
) -> List[Dict[str, Any]]:
    """Stage 1: Fast grid search evaluating only tune_scenario."""
    worker_inputs = [
        (args.config, args.strategy_id, params, df_paths, args.tune_scenario)
        for params in grid
    ]

    results: List[Dict[str, Any]] = []
    best_result: Dict[str, Any] = {}
    start_time = time.time()

    with Pool(processes=num_workers) as pool:
        for i, result in enumerate(
            pool.starmap(run_worker_single_scenario, worker_inputs), 1
        ):
            results.append(result)

            # Always use score_B for consistency across all phases
            if result.get("score_B", float("-inf")) > best_result.get("score_B", float("-inf")):
                best_result = result

            if i % args.progress_every == 0 or i == len(grid):
                elapsed = time.time() - start_time
                _print_progress(i, len(grid), elapsed, best_result, args.show_eta)

    print(f"\nStage 1 complete: {len(results)} evaluated")
    return results


def _run_stage2_topk_evaluation(
    args: argparse.Namespace,
    results_stage1: List[Dict[str, Any]],
    df_paths: Dict[str, str],
    num_workers: int,
) -> List[Dict[str, Any]]:
    """Stage 2: Comprehensive A/B/C evaluation for top-K candidates."""
    df_temp = pd.DataFrame(results_stage1)
    score_col = f"score_{args.tune_scenario}"
    df_sorted = df_temp.sort_values(by=score_col, ascending=False)
    top_k_results_stage1 = df_sorted.head(args.top_k).to_dict("records")

    print(f"Evaluating top {len(top_k_results_stage1)} candidates with full A/B/C scenarios...")

    top_k_params = [r["params"] for r in top_k_results_stage1]
    worker_inputs = [
        (args.config, args.strategy_id, params, df_paths) for params in top_k_params
    ]

    results_topk: List[Dict[str, Any]] = []
    best_result: Dict[str, Any] = {}
    start_time = time.time()

    with Pool(processes=num_workers) as pool:
        for i, result in enumerate(
            pool.starmap(run_worker_full_scenarios, worker_inputs), 1
        ):
            results_topk.append(result)

            if result.get("score_B", float("-inf")) > best_result.get("score_B", float("-inf")):
                best_result = result

            elapsed = time.time() - start_time
            _print_progress(i, len(top_k_params), elapsed, best_result, args.show_eta)

    print(f"\nStage 2 complete: Full A/B/C evaluation done on {len(results_topk)} candidates")
    return results_topk


def _run_single_stage(
    args: argparse.Namespace,
    grid: List[Dict[str, Any]],
    df_paths: Dict[str, str],
    num_workers: int,
) -> List[Dict[str, Any]]:
    """Single stage: Evaluate all candidates with A/B/C."""
    worker_inputs = [
        (args.config, args.strategy_id, params, df_paths) for params in grid
    ]

    results: List[Dict[str, Any]] = []
    best_result: Dict[str, Any] = {}
    start_time = time.time()

    with Pool(processes=num_workers) as pool:
        for i, result in enumerate(pool.imap_unordered(run_worker, worker_inputs), 1):
            results.append(result)

            if result.get("score_B", float("-inf")) > best_result.get("score_B", float("-inf")):
                best_result = result

            if i % args.progress_every == 0 or i == len(grid):
                elapsed = time.time() - start_time
                _print_progress(i, len(grid), elapsed, best_result, args.show_eta)

    print(f"\nEvaluated {len(results)} candidates")
    return results


def _save_results(
    results: List[Dict[str, Any]],
    args: argparse.Namespace,
    out_dir: Path,
) -> None:
    """Save tuning results to CSV and JSON files."""
    df_results = pd.DataFrame([_flatten_result(r) for r in results])
    df_results = df_results.sort_values(
        by=["score_B", "expectancy_B", "max_drawdown_B"],
        ascending=[False, False, True],
    )

    csv_path = out_dir / "tuning_results.csv"
    json_path = out_dir / "tuning_results.json"
    top_k_csv = out_dir / "top_k.csv"
    top_k_json = out_dir / "top_k.json"

    for path in [csv_path, json_path, top_k_csv, top_k_json]:
        if path.exists():
            path.unlink()

    df_results.to_csv(csv_path, index=False)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    top_k_results = results[: args.top_k]
    df_top_k = pd.DataFrame([_flatten_result(r) for r in top_k_results])
    df_top_k.to_csv(top_k_csv, index=False)

    with open(top_k_json, "w", encoding="utf-8") as f:
        json.dump(top_k_results, f, indent=2)

    best = results[0] if results else {}
    print(f"\nBest result:")
    print(f"  Score: {best.get('score_B', 0.0):.4f}")
    print(f"  Params: {best.get('params', {})}")

    print(f"\nOutputs saved to: {out_dir.resolve()}")



if __name__ == "__main__":
    main()
