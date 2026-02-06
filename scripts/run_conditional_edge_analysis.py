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


def _parse_models(raw: str) -> list[str]:
    return [m.strip().lower() for m in raw.split(",") if m.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, help="Path to research_dataset.csv")
    ap.add_argument("--output", default="outputs/conditional_edge_report.json", help="Output report json")
    ap.add_argument("--n_jobs", type=int, default=(os.cpu_count() or 1), help="CPU threads for XGBoost nthread")
    ap.add_argument("--models", default="xgb,logreg", help="Comma-separated model list to run (supported: xgb,logreg)")
    args = ap.parse_args()

    args.n_jobs = max(1, int(args.n_jobs))
    detected_cpus = os.cpu_count() or 1
    print(f"Detected CPU count={detected_cpus}, using n_jobs={args.n_jobs}")

    for env_key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        if env_key not in os.environ:
            os.environ[env_key] = str(args.n_jobs)

    ds_path = Path(args.dataset)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ds = pd.read_csv(ds_path)
    report = run_conditional_edge_analysis(
        ds,
        n_jobs=args.n_jobs,
        models=_parse_models(args.models),
    )

    out_payload = {
        "decision": report["decision"],
        "stability_report": report["stability_report"],
        "feature_importance_stability": _to_records(report["feature_importance_stability"]),
        "per_year_performance": _to_records(report["per_year_performance"]),
        "top_stable_feature_interactions": _to_records(report["top_stable_feature_interactions"]),
        "regions_consistent_ptp_gt_055": _to_records(report["regions_consistent_ptp_gt_055"]),
        "event_types_persistent_skew": _to_records(report["event_types_persistent_skew"]),
        "fold_lift_vs_baseline": _to_records(report["fold_performance"][["fold_id", "test_year", "model", "baseline_tp_rate", "region_tp_rate", "lift_abs", "lift_ratio", "region_coverage", "auc"]]),
        "xgb_top_features_by_fold": _to_records(report["xgb_top_features_by_fold"]),
    }

    out_path.write_text(json.dumps(out_payload, indent=2), encoding="utf-8")
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
