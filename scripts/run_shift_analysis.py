from __future__ import annotations

import argparse

import pandas as pd
from joblib import Parallel, delayed

from edge_discovery.report import build_shift_report
from edge_discovery.shift_tests import compare_event_vs_base
from edge_discovery.stability import yearly_stability


EVENT_COLS = [
    "SWEEP_PREV_DAY_HIGH",
    "SWEEP_PREV_DAY_LOW",
    "IMPULSE_BODY",
    "RANGE_COMPRESSION",
    "VOL_REGIME_SHIFT",
    "EXPANSION_BAR",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="outputs/shift_dataset.csv")
    ap.add_argument("--out", default="outputs/shift_report.json")
    ap.add_argument("--n_jobs", type=int, default=1)
    args = ap.parse_args()

    df = pd.read_csv(args.dataset, index_col=0, parse_dates=True)
    metric_cols = [c for c in df.columns if c.startswith("fwd_")]

    tasks = [(e, m) for e in EVENT_COLS if e in df.columns for m in metric_cols]

    results = Parallel(n_jobs=max(1, int(args.n_jobs)), backend="loky")(
        delayed(compare_event_vs_base)(df, event_col=e, metric_col=m) for e, m in tasks
    )

    yearly_map: dict[tuple[str, str], list[dict]] = {}
    for e, m in tasks:
        yearly_map[(e, m)] = yearly_stability(df, e, m)

    results_df = pd.DataFrame(results)
    build_shift_report(results_df, yearly_map, args.out)
    print(f"Saved: {args.out}")


if __name__ == "__main__":
    main()
