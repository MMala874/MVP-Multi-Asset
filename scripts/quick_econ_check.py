from __future__ import annotations

import argparse

import pandas as pd

from edge_discovery.econ_event_study import run_econ_event_study


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--r_col", required=True)
    ap.add_argument("--horizon", type=int, default=20)
    args = ap.parse_args()

    df = pd.read_parquet(args.dataset) if args.dataset.endswith(".parquet") else pd.read_csv(args.dataset)
    out = run_econ_event_study(df, r_col=args.r_col, horizon=args.horizon)
    h = out["holdout"]
    print(f"E_train={h['E_train']:.6f}")
    print(f"E_holdout={h['E_holdout']:.6f}")
    print(f"CI=[{h['CI_low']:.6f}, {h['CI_high']:.6f}]")
    print(f"pvalue={h['pvalue']:.6f}")
    print(f"neg_year_ratio={h['neg_year_ratio']:.4f}")


if __name__ == "__main__":
    main()
