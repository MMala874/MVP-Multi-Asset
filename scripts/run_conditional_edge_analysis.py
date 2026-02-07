from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd

from edge_discovery.conditional_edge import run_conditional_edge_analysis


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--models", default="xgb,logreg,gb")
    ap.add_argument("--no-xgboost", action="store_true")
    ap.add_argument("--n_jobs", type=int, default=1)
    ap.add_argument("--target_threshold", type=float, default=0.55)
    ap.add_argument("--purge_bars", type=int, default=10)
    ap.add_argument("--rolling_train_years", type=int, default=3)
    ap.add_argument("--rolling_test_years", type=int, default=1)
    ap.add_argument("--holdout_years", type=int, default=1)
    ap.add_argument("--coverage", type=float, default=0.04)
    args = ap.parse_args()

    n_jobs = max(1, args.n_jobs)
    for k in ["OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"]:
        os.environ[k] = str(n_jobs)

    ds = pd.read_csv(args.dataset)
    report = run_conditional_edge_analysis(
        ds,
        models=[m.strip() for m in args.models.split(",") if m.strip()],
        n_jobs=n_jobs,
        coverage=args.coverage,
        target_threshold=args.target_threshold,
        purge_bars=args.purge_bars,
        rolling_train_years=args.rolling_train_years,
        rolling_test_years=args.rolling_test_years,
        holdout_years=args.holdout_years,
        no_xgboost=args.no_xgboost,
    )

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Saved report to {out}")


if __name__ == "__main__":
    main()
