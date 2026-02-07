from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from edge_discovery.conditional_study import (
    block_bootstrap_E,
    compute_expectancy_R,
    distribution_shift_tests,
    permutation_test_labels,
    yearly_stability,
)
from edge_discovery.regime_filters import apply_filter_pack

FORBIDDEN_TOKENS = (
    "fwd",
    "mfe",
    "mae",
    "future",
    "next",
    "resolution",
    "outcome",
    "bars_to_resolution",
    "tp_price",
    "sl_price",
)


def _load_packs(packs_arg: str) -> list[dict[str, Any]]:
    p = Path(packs_arg)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return json.loads(packs_arg)


def _prepare_dataset(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "timestamp" not in df.columns:
        raise ValueError("Dataset must contain 'timestamp'")
    ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.loc[ts.notna()].copy()
    df["timestamp"] = ts[ts.notna()]
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["year"] = df["timestamp"].dt.year.astype(int)

    bad = [c for c in df.columns if any(tok in c.lower() for tok in FORBIDDEN_TOKENS)]
    if bad:
        raise ValueError(f"Forbidden columns found in dataset: {bad}")
    return df


def _candidate_features(df: pd.DataFrame) -> list[str]:
    blacklist = {"label", "timestamp", "year"}
    out = []
    for c in df.columns:
        if c in blacklist:
            continue
        if not pd.api.types.is_numeric_dtype(df[c]):
            continue
        if any(tok in c.lower() for tok in FORBIDDEN_TOKENS):
            continue
        out.append(c)
    return out


def _evaluate_pack(
    train: pd.DataFrame,
    hold: pd.DataFrame,
    pack_name: str,
    pack_filters: dict[str, Any],
    tp_atr: float,
    sl_atr: float,
    min_trades: int,
    B: int,
    block: int,
) -> dict[str, Any] | None:
    train_f, _, _ = apply_filter_pack(train, pack_filters)
    hold_f, _, _ = apply_filter_pack(hold, pack_filters)

    if len(hold_f) < min_trades:
        return None

    train_exp = compute_expectancy_R(train_f, tp_atr=tp_atr, sl_atr=sl_atr)
    hold_exp = compute_expectancy_R(hold_f, tp_atr=tp_atr, sl_atr=sl_atr)
    boot = block_bootstrap_E(hold_f, tp_atr=tp_atr, sl_atr=sl_atr, B=B, block=block, seed=0)
    perm = permutation_test_labels(hold_f, tp_atr=tp_atr, sl_atr=sl_atr, B=B, seed=0)
    stability = yearly_stability(pd.concat([train_f, hold_f], axis=0), tp_atr=tp_atr, sl_atr=sl_atr)

    feature_cols = _candidate_features(pd.concat([train_f, hold_f], axis=0))
    drift_df = pd.concat([train_f.assign(split="train"), hold_f.assign(split="holdout")], axis=0)
    drift = distribution_shift_tests(drift_df, feature_cols)
    top_drift = sorted(
        (
            {"feature": k, **v}
            for k, v in drift.get("features", {}).items()
            if np.isfinite(v.get("ks_pvalue", np.nan))
        ),
        key=lambda x: x["ks_pvalue"],
    )[:5]

    return {
        "pack_name": pack_name,
        "pack": pack_filters,
        "n_train": int(len(train_f)),
        "n_hold": int(len(hold_f)),
        "train": {"p": float(train_exp["p_win"]), "E_R": float(train_exp["E_R"])},
        "holdout": {
            "p": float(hold_exp["p_win"]),
            "E_R": float(hold_exp["E_R"]),
            "ci_low": float(boot["ci_low"]),
            "ci_high": float(boot["ci_high"]),
            "perm_p": float(perm["pvalue"]),
            "bootstrap_p_E_le_0": float(boot["pvalue_E_le_0"]),
        },
        "stability": stability,
        "drift": {
            "pct_features_p001": float(drift.get("pct_features_p001", np.nan)),
            "top_drift_features": top_drift,
        },
    }


def _gate_reasons(result: dict[str, Any]) -> list[str]:
    reasons = []
    if result["holdout"]["E_R"] < 0.05:
        reasons.append("E_R_holdout < 0.05")
    if result["holdout"]["ci_low"] <= 0:
        reasons.append("CI_low <= 0")
    if result["stability"]["neg_year_ratio"] > 0.2:
        reasons.append("neg_year_ratio > 0.2")
    if result["holdout"]["perm_p"] > 0.05:
        reasons.append("permutation_p > 0.05")
    if result["drift"]["pct_features_p001"] > 0.3:
        reasons.append("drift pct_features_p001 > 0.30")
    return reasons


def main() -> None:
    ap = argparse.ArgumentParser(description="Run conditional event edge study (no-ML, leak-free)")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--tp_atr", type=float, required=True)
    ap.add_argument("--sl_atr", type=float, required=True)
    ap.add_argument("--holdout_years", type=int, default=2)
    ap.add_argument("--packs", required=True, help="JSON string or path to JSON file with pack list")
    ap.add_argument("--min_trades", type=int, default=500)
    ap.add_argument("--B", type=int, default=2000)
    ap.add_argument("--block", type=int, default=50)
    ap.add_argument("--out", default="outputs/conditional_study_report.json")
    args = ap.parse_args()

    df = _prepare_dataset(args.dataset)
    packs = _load_packs(args.packs)

    max_year = int(df["year"].max())
    hold_start = max_year - int(args.holdout_years) + 1
    train = df.loc[df["year"] < hold_start].copy()
    hold = df.loc[df["year"] >= hold_start].copy()

    if train.empty or hold.empty:
        raise ValueError("Empty train/holdout split; check holdout_years and dataset coverage")

    results: list[dict[str, Any]] = []
    for i, pack_item in enumerate(packs):
        if isinstance(pack_item, dict) and "filters" in pack_item:
            pack_filters = pack_item["filters"]
            pack_name = str(pack_item.get("name", f"pack_{i:03d}"))
        else:
            pack_filters = pack_item
            pack_name = f"pack_{i:03d}"

        evaluated = _evaluate_pack(
            train=train,
            hold=hold,
            pack_name=pack_name,
            pack_filters=pack_filters,
            tp_atr=args.tp_atr,
            sl_atr=args.sl_atr,
            min_trades=args.min_trades,
            B=args.B,
            block=args.block,
        )
        if evaluated is not None:
            evaluated["gate_failures"] = _gate_reasons(evaluated)
            evaluated["pass"] = len(evaluated["gate_failures"]) == 0
            results.append(evaluated)

    passing = [r for r in results if r["pass"]]
    if passing:
        best = max(passing, key=lambda x: x["holdout"]["E_R"])
        decision = "ACCEPT_EDGE"
        reasons = ["At least one pack passed all acceptance gates"]
    else:
        best = None
        decision = "REJECT_EDGE"
        top5 = sorted(results, key=lambda x: x["holdout"]["E_R"], reverse=True)[:5]
        reasons = [
            "No pack passed all acceptance gates",
            "Top E_R_holdout configs: "
            + "; ".join(f"{r['pack_name']} (fails: {', '.join(r['gate_failures']) or 'n/a'})" for r in top5),
        ]

    report = {
        "decision": decision,
        "reason": reasons,
        "dataset": {
            "rows": int(len(df)),
            "years": sorted(df["year"].unique().astype(int).tolist()),
            "event_name": str(df["event_name"].iloc[0]) if "event_name" in df.columns and len(df) else None,
            "pos_rate": float(pd.to_numeric(df["label"], errors="coerce").mean()),
        },
        "split": {
            "train_years": sorted(train["year"].unique().astype(int).tolist()),
            "holdout_years": sorted(hold["year"].unique().astype(int).tolist()),
        },
        "best_pack": best,
        "results": results,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Saved conditional study report: {out}")


if __name__ == "__main__":
    main()
