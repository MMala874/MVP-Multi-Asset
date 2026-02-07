from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_ohlc_csv(path: str | Path) -> pd.DataFrame:
    """Load OHLC(V) CSV into a UTC-indexed dataframe."""
    df = pd.read_csv(path)
    df.columns = [str(c).strip().lower() for c in df.columns]

    if "time" not in df.columns:
        raise ValueError("CSV must include a 'time' column")

    required = ["open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    df = df.dropna(subset=["time"]).set_index("time")
    df.index = pd.DatetimeIndex(df.index, tz="UTC", name="time")
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]

    cols = ["open", "high", "low", "close"] + (["volume"] if "volume" in df.columns else [])
    out = df[cols].copy()
    for c in cols:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out
