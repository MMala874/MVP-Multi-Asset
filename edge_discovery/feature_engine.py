from __future__ import annotations

import numpy as np
import pandas as pd

from features.indicators import atr

EPS = 1e-12
BARS_PER_DAY_M15 = 96


def _rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(window, min_periods=window).mean()
    std = series.rolling(window, min_periods=window).std()
    return (series - mean) / (std + EPS)


def compute_features(df: pd.DataFrame, events: pd.DataFrame | None = None) -> pd.DataFrame:
    del events
    out = pd.DataFrame(index=df.index)

    open_ = df["open"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    bar_range = high - low
    body = (close - open_).abs()

    hour = df.index.hour + df.index.minute / 60.0
    dow = df.index.dayofweek
    out["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
    out["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
    out["dow_sin"] = np.sin(2 * np.pi * dow / 7.0)
    out["dow_cos"] = np.cos(2 * np.pi * dow / 7.0)
    out["bar_in_day_norm"] = (df.index.hour * 4 + (df.index.minute // 15)) / float(BARS_PER_DAY_M15 - 1)

    atr14 = atr(df, 14).astype(float)
    atr100 = atr(df, 100).astype(float)
    out["atr14"] = atr14
    out["atr100"] = atr100
    out["atr_ratio"] = atr14 / (atr100 + EPS)

    prev_day_high = df["prev_day_high"].astype(float)
    prev_day_low = df["prev_day_low"].astype(float)
    dist_high = (prev_day_high - close) / (atr14 + EPS)
    dist_low = (close - prev_day_low) / (atr14 + EPS)
    out["dist_prev_day_high_z"] = _rolling_zscore(dist_high, 50)
    out["dist_prev_day_low_z"] = _rolling_zscore(dist_low, 50)

    low50 = low.rolling(50, min_periods=50).min()
    high50 = high.rolling(50, min_periods=50).max()
    out["pos_in_range50"] = ((close - low50) / (high50 - low50 + EPS)).clip(0.0, 1.0)

    upper_wick = high - np.maximum(open_, close)
    lower_wick = np.minimum(open_, close) - low
    out["wick_body_ratio"] = (upper_wick + lower_wick) / (body + EPS)
    out["body_range_ratio"] = body / (bar_range + EPS)
    out["close_pos_in_bar"] = ((close - low) / (bar_range + EPS)).clip(0.0, 1.0)

    return out.replace([np.inf, -np.inf], np.nan).astype(np.float64)


compute_normalized_features = compute_features
