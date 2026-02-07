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
    ds = build_research_dataset(ohlc, add_label=True)
    if "label" not in ds.columns:
        raise ValueError("build_research_dataset must produce a 'label' column for conditional edge ML")

    export_df = ds.reset_index(names="timestamp")
    export_df["timestamp"] = export_df["timestamp"].dt.tz_convert("UTC")

    print(export_df.head(5).to_string())
    print(f"Rows: {len(export_df)} | Columns: {len(export_df.columns)}")

    export_df.to_csv(out_dir / "research_dataset.csv", index=False)
    print(f"Saved: {out_dir / 'research_dataset.csv'}")

    try:
        export_df.to_parquet(out_dir / "research_dataset.parquet", index=False)
        print(f"Saved: {out_dir / 'research_dataset.parquet'}")
    except Exception as e:
        print(f"[WARN] Parquet not saved (install pyarrow): {e}")


if __name__ == "__main__":
    main()
