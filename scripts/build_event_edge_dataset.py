from __future__ import annotations

import argparse

from edge_discovery.event_dataset import build_event_dataset, load_ohlc_csv, save_dataset


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--event", default="all")
    ap.add_argument("--tp_atr", type=float, default=1.5)
    ap.add_argument("--sl_atr", type=float, default=1.0)
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--min_event_coverage", type=float, default=0.02)
    ap.add_argument("--max_event_coverage", type=float, default=0.20)
    ap.add_argument("--decision_time", choices=["close", "open_next"], default="close")
    args = ap.parse_args()

    ohlc = load_ohlc_csv(args.csv)
    ds = build_event_dataset(
        ohlc,
        event=args.event,
        tp_atr=args.tp_atr,
        sl_atr=args.sl_atr,
        horizon=args.horizon,
        decision_time=args.decision_time,
        min_event_coverage=args.min_event_coverage,
        max_event_coverage=args.max_event_coverage,
    )
    save_dataset(ds, args.out)

    counts = ds.assign(year=ds.index.year).groupby("year").size().to_dict()
    print(f"rows={len(ds)}")
    print(f"coverage={len(ds) / len(ohlc):.4%}")
    print(f"pos_rate={ds['label'].mean():.4f}")
    print(f"year_counts={counts}")
    print(f"saved={args.out}")


if __name__ == "__main__":
    main()
