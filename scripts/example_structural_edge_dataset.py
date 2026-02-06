"""Example: build a structural edge research dataset from M15 EURUSD data."""

from __future__ import annotations

from data.io import load_ohlc_csv
from edge_discovery.dataset_builder import build_research_dataset


if __name__ == "__main__":
    ohlc = load_ohlc_csv("data/EURUSD_M15.csv")
    ohlc = ohlc.set_index("time")
    if "volume" not in ohlc.columns:
        ohlc["volume"] = 0.0

    dataset = build_research_dataset(ohlc)

    print(dataset.head())
    print(f"Rows: {len(dataset)}")
    print(f"Columns: {len(dataset.columns)}")
