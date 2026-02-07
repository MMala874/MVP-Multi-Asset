from __future__ import annotations

import argparse

from edge_discovery.data_io import load_ohlc_csv
from edge_discovery.dataset_builder import build_research_dataset


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--k_impulse", type=float, default=1.5)
    ap.add_argument("--tp_atr", type=float, default=1.2)
    ap.add_argument("--sl_atr", type=float, default=1.0)
    ap.add_argument("--horizon", type=int, default=10)
    args = ap.parse_args()

    ohlc = load_ohlc_csv(args.csv)
    build_research_dataset(
        ohlc,
        config={
            "k_impulse": args.k_impulse,
            "tp_atr": args.tp_atr,
            "sl_atr": args.sl_atr,
            "horizon": args.horizon,
        },
        out_dir=args.out_dir,
    )


if __name__ == "__main__":
    main()
