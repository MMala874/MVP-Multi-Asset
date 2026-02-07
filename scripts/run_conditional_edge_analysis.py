import argparse
import json
import os
from pathlib import Path

import pandas as pd


def _parse_models(raw: str) -> list[str]:
    return [m.strip().lower() for m in raw.split(",") if m.strip()]


def main():
    detected_cpus = os.cpu_count()
    default_jobs = detected_cpus or 8

    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, help="Path to research_dataset.csv")
    ap.add_argument("--output", default="outputs/conditional_edge_report.json", help="Output report json")
    ap.add_argument("--n_jobs", type=int, default=default_jobs, help="CPU threads for model training")
    ap.add_argument("--models", default="xgb,logreg", help="Comma-separated model list to run (supported: xgb,logreg)")
    ap.add_argument("--target", default="label", help="Column name used as target label source")
    ap.add_argument("--target_mode", choices=["binary_gt0", "binary_threshold", "identity"], default="identity")
    ap.add_argument("--target_threshold", type=float, default=0.0)
    args = ap.parse_args()

    args.n_jobs = max(1, int(args.n_jobs))
    print(f"Detected CPU count={detected_cpus or 0}, using n_jobs={args.n_jobs}")

    for env_key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[env_key] = str(args.n_jobs)

    allowed_models = {"xgb", "logreg"}
    selected_models = _parse_models(args.models)
    unknown = sorted(set(selected_models).difference(allowed_models))
    if unknown:
        raise ValueError(f"Unknown model(s): {', '.join(unknown)}")

    from edge_discovery.conditional_edge import run_conditional_edge_analysis

    ds_path = Path(args.dataset)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ds = pd.read_csv(ds_path)
    report = run_conditional_edge_analysis(
        ds,
        n_jobs=args.n_jobs,
        models=selected_models,
        target_col=args.target,
        target_mode=args.target_mode,
        target_threshold=args.target_threshold,
    )

    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
