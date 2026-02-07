from __future__ import annotations

import pandas as pd

from features.indicators import atr

BARS_PER_DAY_M15 = 96


def _previous_day_levels(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    day = df.index.normalize()
    day_high = df["high"].resample("1D").max().shift(1)
    day_low = df["low"].resample("1D").min().shift(1)
    prev_day_high = pd.Series(day_high.reindex(day).to_numpy(), index=df.index)
    prev_day_low = pd.Series(day_low.reindex(day).to_numpy(), index=df.index)
    return prev_day_high, prev_day_low


def compute_event_flags(
    df: pd.DataFrame,
    k_impulse: float = 1.5,
    vol_regime_ratio: float = 1.8,
    lookback_days: int = 30,
) -> pd.DataFrame:
    lookback_bars = lookback_days * BARS_PER_DAY_M15

    prev_day_high, prev_day_low = _previous_day_levels(df)
    bar_range = (df["high"] - df["low"]).astype(float)
    body = (df["close"] - df["open"]).abs().astype(float)
    atr14 = atr(df, 14)
    atr100 = atr(df, 100)

    std_range10 = bar_range.rolling(10, min_periods=10).std()
    compression_threshold = std_range10.rolling(lookback_bars, min_periods=lookback_bars).quantile(0.2)
    expansion_threshold = bar_range.rolling(lookback_bars, min_periods=lookback_bars).quantile(0.95)

    events = pd.DataFrame(index=df.index)
    events["SWEEP_PREV_DAY_HIGH"] = ((df["high"] > prev_day_high) & (df["close"] < prev_day_high)).astype(int)
    events["SWEEP_PREV_DAY_LOW"] = ((df["low"] < prev_day_low) & (df["close"] > prev_day_low)).astype(int)
    events["IMPULSE_BODY"] = (body > (k_impulse * atr14)).astype(int)
    events["RANGE_COMPRESSION"] = (std_range10 <= compression_threshold).astype(int)
    events["VOL_REGIME_SHIFT"] = ((atr14 / atr100) > vol_regime_ratio).astype(int)
    events["EXPANSION_BAR"] = (bar_range > expansion_threshold).astype(int)

    return events.fillna(0).astype(int)
