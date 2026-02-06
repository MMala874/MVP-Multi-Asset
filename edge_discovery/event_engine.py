from __future__ import annotations

import pandas as pd

from features.indicators import atr

BARS_PER_DAY_M15 = 96


def _validate_ohlcv(df: pd.DataFrame) -> None:
    required = {"open", "high", "low", "close"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing required OHLC columns: {', '.join(sorted(missing))}")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("Input dataframe index must be a DatetimeIndex")


def _previous_day_levels(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    day_high = df["high"].resample("1D").max().shift(1)
    day_low = df["low"].resample("1D").min().shift(1)

    daily_index = df.index.normalize()
    prev_day_high = pd.Series(day_high.reindex(daily_index).to_numpy(), index=df.index)
    prev_day_low = pd.Series(day_low.reindex(daily_index).to_numpy(), index=df.index)
    return prev_day_high, prev_day_low


def compute_event_flags(
    df: pd.DataFrame,
    impulse_k: float = 1.5,
    compression_quantile: float = 0.2,
    compression_window_bars: int = 10,
    lookback_days: int = 30,
    vol_regime_ratio: float = 1.8,
    expansion_quantile: float = 0.9,
) -> pd.DataFrame:
    """Compute anti-lookahead event flags at bar t."""
    _validate_ohlcv(df)

    prev_day_high, prev_day_low = _previous_day_levels(df)

    atr14 = atr(df, 14)
    atr100 = atr(df, 100)
    bar_range = df["high"] - df["low"]
    body = (df["close"] - df["open"]).abs()

    lookback_bars = lookback_days * BARS_PER_DAY_M15
    compression_std = bar_range.rolling(compression_window_bars, min_periods=compression_window_bars).std()
    compression_threshold = compression_std.rolling(lookback_bars, min_periods=lookback_bars).quantile(compression_quantile)
    expansion_threshold = bar_range.rolling(lookback_bars, min_periods=lookback_bars).quantile(expansion_quantile)

    events = pd.DataFrame(index=df.index)
    events["SWEEP_PREV_DAY_HIGH"] = ((df["high"] > prev_day_high) & (df["close"] < prev_day_high)).astype(int)
    events["SWEEP_PREV_DAY_LOW"] = ((df["low"] < prev_day_low) & (df["close"] > prev_day_low)).astype(int)
    events["IMPULSE_BODY"] = (body > (impulse_k * atr14)).astype(int)
    events["RANGE_COMPRESSION"] = (compression_std <= compression_threshold).astype(int)
    events["VOL_REGIME_SHIFT"] = ((atr14 / atr100) > vol_regime_ratio).astype(int)
    events["EXPANSION_BAR"] = (bar_range > expansion_threshold).astype(int)
    return events.fillna(0).astype(int)
