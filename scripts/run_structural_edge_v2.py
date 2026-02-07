from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd

from edge_discovery.conditional_edge import run_conditional_edge_analysis
from edge_discovery.data_io import load_ohlc_csv
from edge_discovery.dataset_builder import build_research_dataset


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out_dir", default="outputs")
    ap.add_argument("--n_jobs", type=int, default=(os.cpu_count() or 1))
    ap.add_argument("--models", default="xgb,logreg,gb")
    ap.add_argument("--no-xgboost", action="store_true")
    args = ap.parse_args()

    n_jobs = max(1, int(args.n_jobs))
    for k in ["OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"]:
        os.environ[k] = str(n_jobs)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ohlc = load_ohlc_csv(args.csv)
    dataset = build_research_dataset(ohlc, out_dir=out_dir)

    dataset_path = out_dir / "research_dataset_v2.csv"
    report_path = out_dir / "conditional_edge_report_v2.json"

    # ensure load path contract is exercised
    ds = pd.read_csv(dataset_path) if dataset_path.exists() else dataset.reset_index(drop=True)
    report = run_conditional_edge_analysis(
        ds,
        models=[m.strip() for m in args.models.split(",") if m.strip()],
        n_jobs=n_jobs,
        coverage=0.04,
        target_threshold=0.55,
        purge_bars=10,
        rolling_train_years=3,
        rolling_test_years=1,
        holdout_years=1,
        no_xgboost=args.no_xgboost,
    )

    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Saved dataset: {dataset_path}")
    print(f"Saved report: {report_path}")


if __name__ == "__main__":
    main()
