from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from data.fx import PIP_SIZES
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
    Merge H1 features to M15 dataframe with backward merge_asof + forward-fill, NO LOOKAHEAD.
    
    H1 features (all shift(1) before merge to ensure closed-bar-only):
    - ema_fast_h1
    - ema_slow_h1
    - adx_h1
    - trend_bias_h1
    
    Double guarantee: prepare_h1_features() shift(1) + merge_asof(direction='backward')
    ensures M15 rows NEVER see current or future H1 bar data, even if timestamps are bar-open.
    Forward-fill used only for start-of-data gaps (safe, no forward injection).
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


def prepare_h1_features(df_h1: pd.DataFrame, ema_fast: int = 50, ema_slow: int = 200, adx_th: float = 20.0, adx_period: int = 14) -> pd.DataFrame:
    """
    Compute H1 trend filter features: EMA, ADX, trend_bias.
    
    CRITICAL: Features are shifted by 1 bar BEFORE returning to ensure no-lookahead.
    This guarantees M15 rows only see the last fully closed H1 bar, even if timestamps
    represent bar-open times.
    
    Args:
        df_h1: H1 OHLC dataframe (raw)
        ema_fast: Fast EMA period (default 50)
        ema_slow: Slow EMA period (default 200)
        adx_th: ADX threshold for trend strength (default 20.0)
        adx_period: ADX period (default 14)
    
    Returns:
        H1 dataframe with columns: [time, ema_fast_h1, ema_slow_h1, adx_h1, trend_bias_h1]
        All features are shift(1) to ensure they represent CLOSED bars only.
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
    
    # ANTI-LOOKAHEAD: Shift all H1 features by 1 bar so M15 only sees closed H1 bars
    # If timestamps are bar-open times, shift(1) ensures we never use current bar's data
    h1_feature_cols = ["ema_fast_h1", "ema_slow_h1", "adx_h1", "trend_bias_h1"]
    for col in h1_feature_cols:
        df[col] = df[col].shift(1)
    
    # Return only required columns for merge
    return df[["time", "ema_fast_h1", "ema_slow_h1", "adx_h1", "trend_bias_h1"]].copy()


def prepare_h1_features_with_atr(df_h1: pd.DataFrame, symbol: str, ema_fast: int = 50, ema_slow: int = 200, adx_th: float = 20.0, adx_period: int = 14, atr_period: int = 14) -> pd.DataFrame:
    """
    Compute H1 features including ATR in PIPS.
    
    CRITICAL: All features shifted by 1 bar BEFORE returning (closed-bar-only, no lookahead).
    
    Args:
        df_h1: H1 OHLC dataframe (raw)
        symbol: Symbol for pip size conversion (e.g., "EURUSD")
        ema_fast: Fast EMA period (default 50)
        ema_slow: Slow EMA period (default 200)
        adx_th: ADX threshold for trend strength (default 20.0)
        adx_period: ADX period (default 14)
        atr_period: ATR period (default 14)
    
    Returns:
        H1 dataframe with columns: [time, ema_fast_h1, ema_slow_h1, adx_h1, trend_bias_h1, atr_h1_pips]
        All features are shift(1) to ensure they represent CLOSED bars only.
    """
    df = df_h1.copy()
    
    # Compute fast and slow EMAs
    df["ema_fast_h1"] = ema(df["close"], ema_fast)
    df["ema_slow_h1"] = ema(df["close"], ema_slow)
    
    # Compute ADX
    df["adx_h1"] = adx(df, adx_period)
    
    # Derive trend_bias_h1
    df["trend_bias_h1"] = np.where(
        (df["ema_fast_h1"] > df["ema_slow_h1"]) & (df["adx_h1"] > adx_th),
        1.0,  # LONG
        np.where(
            (df["ema_fast_h1"] < df["ema_slow_h1"]) & (df["adx_h1"] > adx_th),
            -1.0,  # SHORT
            0.0  # FLAT
        )
    )
    
    # Compute ATR in price units
    df["atr_h1"] = atr(df, atr_period)
    
    # Convert ATR to pips
    pip_size = PIP_SIZES.get(symbol, 0.0001)
    df["atr_h1_pips"] = df["atr_h1"] / pip_size
    
    # ANTI-LOOKAHEAD: Shift all H1 features by 1 bar
    h1_feature_cols = ["ema_fast_h1", "ema_slow_h1", "adx_h1", "trend_bias_h1", "atr_h1_pips"]
    for col in h1_feature_cols:
        df[col] = df[col].shift(1)
    
    # Return only required columns for merge
    return df[["time", "ema_fast_h1", "ema_slow_h1", "adx_h1", "trend_bias_h1", "atr_h1_pips"]].copy()


def prepare_h4_features(df_h4: pd.DataFrame, symbol: str, ema_fast: int = 50, ema_slow: int = 200, adx_period: int = 14, adx_min: float = 20.0) -> pd.DataFrame:
    """
    Compute H4 trend features for use as directional bias in multi-timeframe strategies.
    
    CRITICAL: All features shifted by 1 bar BEFORE returning (closed-bar-only, no lookahead).
    
    Args:
        df_h4: H4 OHLC dataframe (raw)
        symbol: Symbol for pip size conversion (e.g., "EURUSD")
        ema_fast: Fast EMA period (default 50)
        ema_slow: Slow EMA period (default 200)
        adx_period: ADX period (default 14)
        adx_min: Minimum ADX threshold for valid trend (default 20.0)
    
    Returns:
        H4 dataframe with columns: [time, ema_fast_h4, ema_slow_h4, adx_h4, trend_bias_h4]
        All features are shift(1) to ensure they represent CLOSED bars only.
        
        trend_bias_h4:
        +1 if ema_fast_h4 > ema_slow_h4 AND adx_h4 >= adx_min
        -1 if ema_fast_h4 < ema_slow_h4 AND adx_h4 >= adx_min
         0 otherwise (FLAT)
    """
    df = df_h4.copy()
    
    # Compute fast and slow EMAs
    df["ema_fast_h4"] = ema(df["close"], ema_fast)
    df["ema_slow_h4"] = ema(df["close"], ema_slow)
    
    # Compute ADX
    df["adx_h4"] = adx(df, adx_period)
    
    # Derive trend_bias_h4: directional bias only if ADX strong
    df["trend_bias_h4"] = np.where(
        (df["ema_fast_h4"] > df["ema_slow_h4"]) & (df["adx_h4"] >= adx_min),
        1.0,  # LONG: fast > slow AND trend strong
        np.where(
            (df["ema_fast_h4"] < df["ema_slow_h4"]) & (df["adx_h4"] >= adx_min),
            -1.0,  # SHORT: fast < slow AND trend strong
            0.0  # FLAT: no valid trend
        )
    )
    
    # ANTI-LOOKAHEAD: Shift all H4 features by 1 bar
    h4_feature_cols = ["ema_fast_h4", "ema_slow_h4", "adx_h4", "trend_bias_h4"]
    for col in h4_feature_cols:
        df[col] = df[col].shift(1)
    
    # Return only required columns for merge
    return df[["time", "ema_fast_h4", "ema_slow_h4", "adx_h4", "trend_bias_h4"]].copy()


def merge_h4_to_m15(df_m15: pd.DataFrame, df_h4: pd.DataFrame) -> pd.DataFrame:
    """
    Merge H4 features to M15 dataframe with backward merge_asof + forward-fill, NO LOOKAHEAD.
    
    H4 features (all shift(1) before merge to ensure closed-bar-only):
    - ema_fast_h4
    - ema_slow_h4
    - adx_h4
    - trend_bias_h4
    
    Double guarantee: prepare_h4_features() shift(1) + merge_asof(direction='backward')
    ensures M15 rows NEVER see current or future H4 bar data, even if timestamps are bar-open.
    Forward-fill used only for start-of-data gaps (safe, no forward injection).
    """
    df = df_m15.copy()
    
    # Ensure time columns are datetime
    df["time"] = pd.to_datetime(df["time"])
    df_h4["time"] = pd.to_datetime(df_h4["time"])
    
    # H4 features to merge
    h4_cols = ["ema_fast_h4", "ema_slow_h4", "adx_h4", "trend_bias_h4"]
    
    # Keep only time + H4 features from H4 dataframe
    df_h4_features = df_h4[["time"] + [c for c in h4_cols if c in df_h4.columns]].copy()
    
    # Merge: left join (M15 as left, H4 as right)
    # This ensures no future H4 data is pulled
    df = pd.merge_asof(
        df,
        df_h4_features,
        on="time",
        direction="backward"  # backward fill: use most recent H4 bar <= current M15 bar
    )
    
    # Forward-fill any remaining gaps (rare, at start of data)
    for col in h4_cols:
        if col in df.columns:
            df[col] = df[col].ffill()
    
    # Validate that trend_bias_h4 was actually merged
    if "trend_bias_h4" not in df.columns or df["trend_bias_h4"].isna().all():
        raise ValueError("H4 trend_bias_h4 not properly merged; M15 data range may not overlap with H4")
    
    return df


def merge_h1_to_m15_with_atr(df_m15: pd.DataFrame, df_h1: pd.DataFrame) -> pd.DataFrame:
    """
    Merge H1 features (including ATR in pips) to M15 dataframe with backward merge_asof + forward-fill, NO LOOKAHEAD.
    
    H1 features (all shift(1) before merge to ensure closed-bar-only):
    - ema_fast_h1
    - ema_slow_h1
    - adx_h1
    - trend_bias_h1
    - atr_h1_pips (ATR in pip units, ready to use as sl_points)
    
    Double guarantee: prepare_h1_features_with_atr() shift(1) + merge_asof(direction='backward')
    ensures M15 rows NEVER see current or future H1 bar data, even if timestamps are bar-open.
    Forward-fill used only for start-of-data gaps (safe, no forward injection).
    """
    df = df_m15.copy()
    
    # Ensure time columns are datetime
    df["time"] = pd.to_datetime(df["time"])
    df_h1["time"] = pd.to_datetime(df_h1["time"])
    
    # H1 features to merge
    h1_cols = ["ema_fast_h1", "ema_slow_h1", "adx_h1", "trend_bias_h1", "atr_h1_pips"]
    
    # Keep only time + H1 features from H1 dataframe
    df_h1_features = df_h1[["time"] + [c for c in h1_cols if c in df_h1.columns]].copy()
    
    # Merge: left join (M15 as left, H1 as right)
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