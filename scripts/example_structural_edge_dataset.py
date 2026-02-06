import argparse
from pathlib import Path

from edge_discovery.dataset_builder import build_research_dataset
from edge_discovery.data_io import load_ohlc_csv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="Path to OHLCV CSV (M15)")
    ap.add_argument("--out_dir", default="outputs", help="Output directory")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ohlc = load_ohlc_csv(args.csv)
    ds = build_research_dataset(ohlc)

    print(ds.head(5).to_string())
    print(f"Rows: {len(ds)} | Columns: {len(ds.columns)}")

    # IMPORTANT: avoid writing index into CSV, otherwise a string 'time' column appears
    # and breaks downstream float conversion.
    ds.to_csv(out_dir / "research_dataset.csv", index=False)
    print(f"Saved: {out_dir / 'research_dataset.csv'}")

    try:
        ds.to_parquet(out_dir / "research_dataset.parquet")
        print(f"Saved: {out_dir / 'research_dataset.parquet'}")
    except Exception as e:
        print(f"[WARN] Parquet not saved (install pyarrow): {e}")

if __name__ == "__main__":
    main()
