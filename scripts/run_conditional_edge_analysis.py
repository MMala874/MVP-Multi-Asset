from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd

from edge_discovery.conditional_edge import run_conditional_edge_analysis


def _to_records(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_float_dtype(out[c]):
            out[c] = out[c].round(6)
    return out.to_dict(orient="records")


def main() -> None:
    parser = argparse.ArgumentParser(description="Conditional edge discovery analysis on structural dataset")
    parser.add_argument("--dataset", required=True, help="Path to research dataset CSV (must include label)")
    parser.add_argument("--output", default="outputs/conditional_edge_report.json", help="Output JSON report path")
    parser.add_argument("--no-xgboost", action="store_true", help="Disable XGBoost model")
    parser.add_argument(
        "--n_jobs",
        type=int,
        default=max(1, (os.cpu_count() or 1) - 2),
        help="Number of CPU workers for supported models (default: max(1, os.cpu_count()-2))",
    )
    args = parser.parse_args()

    ds = pd.read_csv(args.dataset)
    report = run_conditional_edge_analysis(ds, include_xgboost=not args.no_xgboost, n_jobs=args.n_jobs)

    out_payload = {
        "decision": report["decision"],
        "stability_report": report["stability_report"],
        "feature_importance_stability": _to_records(report["feature_importance_stability"]),
        "per_year_performance": _to_records(report["per_year_performance"]),
        "top_stable_feature_interactions": _to_records(report["top_stable_feature_interactions"]),
        "regions_consistent_ptp_gt_055": _to_records(report["regions_consistent_ptp_gt_055"]),
        "event_types_persistent_skew": _to_records(report["event_types_persistent_skew"]),
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_payload, indent=2), encoding="utf-8")

    print(f"Decision: {report['decision']}")
    print(f"Saved report: {out_path}")


if __name__ == "__main__":
    main()
