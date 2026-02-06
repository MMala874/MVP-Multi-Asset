"""Build a structural edge research dataset from M15 OHLCV and save to disk."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from data.io import load_ohlc_csv
from edge_discovery.dataset_builder import build_research_dataset


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="Path to EURUSD M15 OHLCV CSV")
    ap.add_argument("--out_dir", default="outputs", help="Output directory")
    ap.add_argument("--out_name", default="research_dataset.csv", help="Output CSV filename")
    ap.add_argument("--tz_utc", action="store_true", help="Force UTC timestamps when parsing")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / args.out_name

    ohlc = load_ohlc_csv(args.csv)
    if "time" not in ohlc.columns:
        raise ValueError("Input CSV must contain a 'time' column")
    ohlc = ohlc.set_index("time")

    # Safety: volume optional
    if "volume" not in ohlc.columns:
        ohlc["volume"] = 0.0

    dataset = build_research_dataset(ohlc)

    # Always save CSV (works everywhere)
    dataset.to_csv(out_path, index=True)
    print(dataset.head())
    print(f"Rows: {len(dataset)} | Columns: {len(dataset.columns)}")
    print(f"Saved: {out_path}")

    # Optional parquet if available
    try:
        dataset.to_parquet(out_dir / "research_dataset.parquet", index=True)
        print(f"Saved: {out_dir / 'research_dataset.parquet'}")
    except Exception as e:
        print(f"[warn] Parquet not saved (install pyarrow/fastparquet). Reason: {e}")


if __name__ == "__main__":
    main()
