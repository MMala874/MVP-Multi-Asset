from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from features.indicators import ema, atr, adx


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

def merge_h1_to_m15(df_m15: pd.DataFrame, df_h1: pd.DataFrame) -> pd.DataFrame:
    """
    Merge H1 features to M15 dataframe with forward-fill, NO LOOKAHEAD.
    
    H1 features are:
    - ema_fast_h1
    - ema_slow_h1
    - adx_h1
    - trend_bias_h1
    
    Merge via 'time' column, forward-fill gaps, ensure no future H1 data visible.
    """
    df = df_m15.copy()
    
    # Ensure time columns are datetime
    df["time"] = pd.to_datetime(df["time"])
    df_h1["time"] = pd.to_datetime(df_h1["time"])
    
    # H1 features to merge
    h1_cols = ["ema_fast_h1", "ema_slow_h1", "adx_h1", "trend_bias_h1"]
    
    # Keep only time + H1 features from H1 dataframe
    df_h1_features = df_h1[["time"] + [c for c in h1_cols if c in df_h1.columns]].copy()
    
    # Merge: left join (M15 as left, H1 as right)
    # This ensures no future H1 data is pulled
    df = pd.merge_asof(
        df,
        df_h1_features,
        on="time",
        direction="backward"  # backward fill: use most recent H1 bar <= current M15 bar
    )
    
    # Forward-fill any remaining gaps (rare, at start of data)
    for col in h1_cols:
        if col in df.columns:
            df[col] = df[col].ffill()
    
    return df


def prepare_h1_features(df_h1: pd.DataFrame, ema_fast: int = 8, ema_slow: int = 21, adx_th: float = 25.0, adx_period: int = 14) -> pd.DataFrame:
    """
    Compute H1 trend filter features: EMA, ADX, trend_bias.
    
    Args:
        df_h1: H1 OHLC dataframe (raw)
        ema_fast: Fast EMA period (default 8)
        ema_slow: Slow EMA period (default 21)
        adx_th: ADX threshold for trend strength (default 25.0)
        adx_period: ADX period (default 14)
    
    Returns:
        H1 dataframe with columns: [time, ema_fast_h1, ema_slow_h1, adx_h1, trend_bias_h1]
    """
    df = df_h1.copy()
    
    # Compute fast and slow EMAs (need to pass close series, not dataframe)
    df["ema_fast_h1"] = ema(df["close"], ema_fast)
    df["ema_slow_h1"] = ema(df["close"], ema_slow)
    
    # Compute ADX
    df["adx_h1"] = adx(df, adx_period)
    
    # Derive trend_bias_h1
    # LONG: fast EMA > slow EMA AND ADX > threshold
    # SHORT: fast EMA < slow EMA AND ADX > threshold
    # FLAT: otherwise
    df["trend_bias_h1"] = np.where(
        (df["ema_fast_h1"] > df["ema_slow_h1"]) & (df["adx_h1"] > adx_th),
        1.0,  # LONG
        np.where(
            (df["ema_fast_h1"] < df["ema_slow_h1"]) & (df["adx_h1"] > adx_th),
            -1.0,  # SHORT
            0.0  # FLAT
        )
    )
    
    # Return only required columns for merge
    return df[["time", "ema_fast_h1", "ema_slow_h1", "adx_h1", "trend_bias_h1"]].copy()