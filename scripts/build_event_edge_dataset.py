from __future__ import annotations

import argparse
from itertools import product

import pandas as pd

from edge_discovery.distributional import forward_returns, triple_barrier_expectancy
from edge_discovery.event_dataset import build_event_dataset, load_ohlc_csv, save_dataset


FORBIDDEN_TOKENS = ("fwd", "mfe", "mae", "resolution", "outcome", "future", "next", "tp", "sl", "diag")
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
    ap.add_argument("--label_mode", choices=["triple_barrier", "tp_sl_first", "range_expansion", "directional_expansion"], default="triple_barrier")
    ap.add_argument("--min_event_coverage", type=float, default=0.02)
    ap.add_argument("--max_event_coverage", type=float, default=0.20)
    ap.add_argument("--decision_time", choices=["close", "open_next"], default="close")
    ap.add_argument("--reclaim_bars", type=int, default=None)
    ap.add_argument("--confirm_bars", type=int, default=None)
    ap.add_argument("--within_bars", type=int, default=None)
    ap.add_argument("--fill_bars", type=int, default=None)
    ap.add_argument("--compress_window", type=int, default=96)
    ap.add_argument("--compress_q", type=float, default=0.10)
    ap.add_argument("--expand_k", type=float, default=None)
    ap.add_argument("--expand_lookahead_N", type=int, default=None)
    ap.add_argument("--dir_k", type=float, default=1.0)
    ap.add_argument("--range_k", type=float, default=2.0)
    ap.add_argument("--add_distributional", action="store_true")
    ap.add_argument("--dist_horizons", default=None)
    ap.add_argument("--dist_atr_multiples", default="1.0,1.5")
    ap.add_argument("--slippage_pips", type=float, default=0.0)
    ap.add_argument("--spread_mode", choices=["none", "column", "fixed"], default=None)
    ap.add_argument("--fixed_spread_pips", type=float, default=0.7)
    args = ap.parse_args()

    event_config = {
        k: v
        for k, v in {
            "reclaim_bars": args.reclaim_bars,
            "confirm_bars": args.confirm_bars,
            "within_bars": args.within_bars,
            "fill_bars": args.fill_bars,
            "compress_window": args.compress_window,
            "compress_q": args.compress_q,
            "expand_k": args.expand_k,
            "expand_lookahead_N": args.expand_lookahead_N,
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
        label_mode=args.label_mode,
        dir_k=args.dir_k,
        range_k=args.range_k,
    )

    diag_df = None
    if args.add_distributional:
        spread_mode = args.spread_mode or ("column" if "spread" in ohlc.columns else "fixed")
        horizons = [int(x.strip()) for x in (args.dist_horizons or str(args.horizon)).split(",") if x.strip()]
        atr_mults = [float(x.strip()) for x in args.dist_atr_multiples.split(",") if x.strip()]
        idx = pd.to_datetime(ds["timestamp"], utc=True, errors="coerce")

        diag_df = pd.DataFrame(index=ds.index)
        diag_df["timestamp"] = ds["timestamp"]
        for h in horizons:
            fwd = forward_returns(ohlc, horizon=h)
            diag_df[f"diag_fwd_ret_{h}"] = fwd.reindex(idx).to_numpy()

            event_mask = ohlc.index.isin(idx)
            for tp, sl in product(atr_mults, atr_mults):
                tb = triple_barrier_expectancy(
                    ohlc,
                    event_mask=event_mask,
                    horizon=h,
                    tp_atr=tp,
                    sl_atr=sl,
                    decision_time=args.decision_time,
                    slippage_pips=args.slippage_pips,
                    spread_mode=spread_mode,
                    fixed_spread_pips=args.fixed_spread_pips,
                )
                key = f"tp{tp:g}_sl{sl:g}_H{h}"
                aligned = tb.reindex(idx)
                diag_df[f"diag_r_mult_{key}"] = aligned["r_mult"].to_numpy()
                diag_df[f"diag_hit_{key}"] = aligned["hit_type"].to_numpy()

    ds = _drop_diagnostic_columns(ds)
    save_dataset(ds, args.out)
    if diag_df is not None:
        diag_out = f"{args.out}.diag.csv"
        save_dataset(diag_df, diag_out)

    counts = ds.assign(year=ds.index.year).groupby("year").size().to_dict()
    print(f"rows={len(ds)}")
    print(f"coverage={len(ds) / len(ohlc):.4%}")
    print(f"pos_rate={ds['label'].mean():.4f}")
    print(f"year_counts={counts}")
    print(f"label_mode={args.label_mode}")
    print(f"event_name={args.event}")
    print("event_engine=causal_state_machine")
    print(f"saved={args.out}")


if __name__ == "__main__":
    main()
