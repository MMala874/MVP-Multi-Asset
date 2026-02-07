from __future__ import annotations

import argparse

from edge_discovery.event_dataset import build_event_dataset, load_ohlc_csv, save_dataset


FORBIDDEN_TOKENS = ("fwd", "mfe", "mae", "resolution", "outcome", "future", "next", "tp", "sl")
FORBIDDEN_EXACT = {"bars_to_resolution", "outcome_type"}


def _drop_diagnostic_columns(df):
    forbidden = [
        c
        for c in df.columns
        if c in FORBIDDEN_EXACT or any(tok in c.lower() for tok in FORBIDDEN_TOKENS)
    ]
    return df.drop(columns=forbidden, errors="ignore")


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
    ap.add_argument("--reclaim_bars", type=int, default=None)
    ap.add_argument("--confirm_bars", type=int, default=None)
    ap.add_argument("--within_bars", type=int, default=None)
    ap.add_argument("--fill_bars", type=int, default=None)
    args = ap.parse_args()

    event_config = {
        k: v
        for k, v in {
            "reclaim_bars": args.reclaim_bars,
            "confirm_bars": args.confirm_bars,
            "within_bars": args.within_bars,
            "fill_bars": args.fill_bars,
        }.items()
        if v is not None
    }

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
        event_config=event_config or None,
    )
    ds = _drop_diagnostic_columns(ds)
    save_dataset(ds, args.out)

    counts = ds.assign(year=ds.index.year).groupby("year").size().to_dict()
    print(f"rows={len(ds)}")
    print(f"coverage={len(ds) / len(ohlc):.4%}")
    print(f"pos_rate={ds['label'].mean():.4f}")
    print(f"year_counts={counts}")
    print("event_engine=causal_state_machine")
    print(f"saved={args.out}")


if __name__ == "__main__":
    main()
