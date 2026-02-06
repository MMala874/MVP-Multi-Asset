from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from edge_discovery.dataset_builder import build_shift_dataset


def load_ohlcv_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], utc=False)
        df = df.set_index("time")
    elif isinstance(df.index, pd.RangeIndex):
        raise ValueError("CSV must include a 'time' column")

    df.index = pd.to_datetime(df.index)
    cols = ["open", "high", "low", "close"]
    optional = ["volume"]
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    for c in cols + [c for c in optional if c in df.columns]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_index()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out_dir", default="outputs")
    ap.add_argument("--add_label", action="store_true", help="Add double-barrier label column")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ohlcv = load_ohlcv_csv(args.csv)
    dataset = build_shift_dataset(ohlcv, add_label=args.add_label)

    csv_path = out_dir / "shift_dataset.csv"
    dataset.to_csv(csv_path, index=True)
    print(f"Saved: {csv_path}")

    parquet_path = out_dir / "shift_dataset.parquet"
    try:
        dataset.to_parquet(parquet_path)
        print(f"Saved: {parquet_path}")
    except Exception as exc:
        print(f"[WARN] Parquet save skipped: {exc}")


if __name__ == "__main__":
    main()
