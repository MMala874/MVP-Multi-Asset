from __future__ import annotations

import numpy as np
import pandas as pd

from features.indicators import atr, ema

EPS = 1e-12
BARS_PER_DAY_M15 = 96


def _zscore(series: pd.Series, window: int) -> pd.Series:
    m = series.rolling(window, min_periods=max(10, window // 2)).mean()
    s = series.rolling(window, min_periods=max(10, window // 2)).std()
    return (series - m) / s


def _rolling_linreg_log_close(close: pd.Series, window: int = 20) -> tuple[pd.Series, pd.Series]:
    x = np.arange(window, dtype=np.float64)
    x_center = x - x.mean()
    denom = np.sum(x_center**2)

    def slope(arr: np.ndarray) -> float:
        y = arr - arr.mean()
        return float(np.sum(x_center * y) / denom)

    def r2(arr: np.ndarray) -> float:
        y = arr
        b1 = slope(arr)
        b0 = y.mean() - b1 * x.mean()
        pred = b0 + b1 * x
        ss_res = float(np.sum((y - pred) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        return 0.0 if ss_tot <= EPS else 1.0 - ss_res / ss_tot

    log_close = np.log(close.clip(lower=EPS))
    return (
        log_close.rolling(window, min_periods=window).apply(slope, raw=True),
        log_close.rolling(window, min_periods=window).apply(r2, raw=True),
    )


def _prev_day_levels(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    day = df.index.normalize()
    prev_h = df["high"].resample("1D").max().shift(1)
    prev_l = df["low"].resample("1D").min().shift(1)
    return (
        pd.Series(prev_h.reindex(day).to_numpy(), index=df.index),
        pd.Series(prev_l.reindex(day).to_numpy(), index=df.index),
    )


def compute_features(df: pd.DataFrame, events: pd.DataFrame | None = None, lookback_days: int = 30) -> pd.DataFrame:
    del events
    out = pd.DataFrame(index=df.index)
    close, open_, high, low = df["close"], df["open"], df["high"], df["low"]
    bar_range = high - low
    body = (close - open_).abs()

    # time structure
    hour = df.index.hour + (df.index.minute / 60.0)
    dow = df.index.dayofweek
    out["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
    out["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
    out["dow_sin"] = np.sin(2 * np.pi * dow / 7.0)
    out["dow_cos"] = np.cos(2 * np.pi * dow / 7.0)
    out["bar_in_day_norm"] = ((df.index.hour * 4 + (df.index.minute // 15)) / float(BARS_PER_DAY_M15 - 1)).astype(float)

    # vol structure
    atr14 = atr(df, 14)
    atr100 = atr(df, 100)
    out["atr_ratio"] = atr14 / atr100
    rv20 = close.pct_change().rolling(20, min_periods=20).std()
    out["vol_z20"] = _zscore(rv20, 50)
    std_range10 = bar_range.rolling(10, min_periods=10).std()
    out["compression_score"] = _zscore(std_range10, lookback_days * BARS_PER_DAY_M15)

    # trend structure
    ema50 = ema(close, 50)
    out["ema50_slope_norm"] = (ema50 - ema50.shift(1)) / close.shift(1)
    out["reg_slope_20"], out["reg_r2_20"] = _rolling_linreg_log_close(close, 20)

    # position structure
    low50 = low.rolling(50, min_periods=25).min()
    high50 = high.rolling(50, min_periods=25).max()
    out["pos_in_range50"] = ((close - low50) / (high50 - low50 + EPS)).clip(0.0, 1.0)
    prev_day_high, prev_day_low = _prev_day_levels(df)
    out["dist_prev_day_high_z"] = _zscore((prev_day_high - close) / (atr14 + EPS), 50)
    out["dist_prev_day_low_z"] = _zscore((close - prev_day_low) / (atr14 + EPS), 50)
    upper_wick = high - np.maximum(open_, close)
    lower_wick = np.minimum(open_, close) - low
    out["wick_body_ratio"] = (upper_wick + lower_wick) / (body + EPS)
    out["body_range_ratio"] = body / (bar_range + EPS)
    out["close_pos_in_bar"] = ((close - low) / (bar_range + EPS)).clip(0.0, 1.0)

    out = out.replace([np.inf, -np.inf], np.nan).astype(np.float32)
    return out


compute_normalized_features = compute_features
