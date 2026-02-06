from __future__ import annotations

import numpy as np
import pandas as pd

from features.indicators import atr

BARS_PER_DAY_M15 = 96


def _validate_ohlcv(df: pd.DataFrame) -> None:
    required = {"open", "high", "low", "close", "volume"}
    missing = required.difference(df.columns)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"Missing required OHLCV columns: {missing_text}")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("Input dataframe index must be a DatetimeIndex")


def _previous_day_levels(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    day_high = df["high"].resample("1D").max()
    day_low = df["low"].resample("1D").min()

    prev_day_high_daily = day_high.shift(1)
    prev_day_low_daily = day_low.shift(1)

    daily_index = df.index.normalize()
    prev_day_high = pd.Series(prev_day_high_daily.reindex(daily_index).to_numpy(), index=df.index)
    prev_day_low = pd.Series(prev_day_low_daily.reindex(daily_index).to_numpy(), index=df.index)
    return prev_day_high, prev_day_low


def compute_event_flags(
    df: pd.DataFrame,
    impulse_k: float = 1.5,
    compression_percentile: float = 0.2,
    compression_window_bars: int = 10,
    compression_lookback_days: int = 30,
) -> pd.DataFrame:
    """Build binary event flags for structural edge research.

    All computations are backward-looking only.
    """
    _validate_ohlcv(df)

    prev_day_high, prev_day_low = _previous_day_levels(df)

    atr14 = atr(df, 14)
    atr100 = atr(df, 100)

    bar_range = df["high"] - df["low"]
    body = (df["close"] - df["open"]).abs()

    compression_std = bar_range.rolling(
        window=compression_window_bars,
        min_periods=compression_window_bars,
    ).std()
    compression_lookback_bars = compression_lookback_days * BARS_PER_DAY_M15
    compression_threshold = compression_std.rolling(
        window=compression_lookback_bars,
        min_periods=compression_lookback_bars,
    ).quantile(compression_percentile)

    events = pd.DataFrame(index=df.index)
    events["SWEEP_PREV_DAY_HIGH"] = (
        (df["high"] > prev_day_high) & (df["close"] < prev_day_high)
    ).astype(int)
    events["SWEEP_PREV_DAY_LOW"] = (
        (df["low"] < prev_day_low) & (df["close"] > prev_day_low)
    ).astype(int)
    events["IMPULSE_BODY"] = (body > (impulse_k * atr14)).astype(int)
    events["RANGE_COMPRESSION"] = (compression_std <= compression_threshold).astype(int)
    events["VOL_REGIME_SHIFT"] = ((atr14 / atr100) > 1.8).astype(int)

    return events.fillna(0).astype(int)
