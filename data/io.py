from __future__ import annotations

from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = ["time", "open", "high", "low", "close"]


def load_ohlc_csv(path: str | Path) -> pd.DataFrame:
    """Load OHLC CSV data with standardized columns and dtypes."""
    df = pd.read_csv(path)
    df = df[REQUIRED_COLUMNS].copy()
    df["time"] = pd.to_datetime(df["time"], errors="raise")
    for column in ["open", "high", "low", "close"]:
        df[column] = df[column].astype(float)
    df = df.sort_values("time").reset_index(drop=True)
    return df
