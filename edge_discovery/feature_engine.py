from __future__ import annotations

import numpy as np
import pandas as pd

from features.indicators import atr, ema

EPS = 1e-12
BARS_PER_DAY_M15 = 96


def _rolling_slope_r2(series: pd.Series, window: int) -> tuple[pd.Series, pd.Series]:
    x = np.arange(window, dtype=float)
    x_centered = x - x.mean()
    denom = float((x_centered**2).sum())

    def _slope(values: np.ndarray) -> float:
        y_centered = values - values.mean()
        return float((x_centered * y_centered).sum() / denom)

    def _r2(values: np.ndarray) -> float:
        y = values
        slope = _slope(y)
        intercept = y.mean() - slope * x.mean()
        fitted = slope * x + intercept
        ss_res = float(((y - fitted) ** 2).sum())
        ss_tot = float(((y - y.mean()) ** 2).sum())
        return 0.0 if ss_tot <= EPS else float(1.0 - (ss_res / ss_tot))

    return (
        series.rolling(window=window, min_periods=window).apply(_slope, raw=True),
        series.rolling(window=window, min_periods=window).apply(_r2, raw=True),
    )


def compute_features(df: pd.DataFrame, lookback_days: int = 30) -> pd.DataFrame:
    """Compute backward-only normalized features (no raw price levels)."""
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("Input dataframe index must be a DatetimeIndex")

    close = df["close"]
    open_ = df["open"]
    high = df["high"]
    low = df["low"]

    bar_range = high - low
    body = (close - open_).abs()

    atr14 = atr(df, 14)
    atr100 = atr(df, 100)
    returns = close.pct_change()
    lookback_bars = lookback_days * BARS_PER_DAY_M15

    # Regime
    range_std_10 = bar_range.rolling(10, min_periods=10).std()
    compression_q20 = range_std_10.rolling(lookback_bars, min_periods=lookback_bars).quantile(0.2)
    compression_score = (compression_q20 - range_std_10) / (compression_q20.abs() + EPS)

    vol20 = returns.rolling(20, min_periods=20).std()
    vol20_mean = vol20.rolling(20, min_periods=20).mean()
    vol20_std = vol20.rolling(20, min_periods=20).std()

    # Trend
    ema50 = ema(close, 50)
    ema50_slope = (ema50 - ema50.shift(20)) / 20.0

    reg_slope_20, reg_r2_20 = _rolling_slope_r2(np.log(close.clip(lower=EPS)), window=20)

    # Position
    rolling_low_50 = low.rolling(50, min_periods=50).min()
    rolling_high_50 = high.rolling(50, min_periods=50).max()

    day_high_prev = high.resample("1D").max().shift(1)
    day_low_prev = low.resample("1D").min().shift(1)
    prev_day_high = pd.Series(day_high_prev.reindex(df.index.normalize()).to_numpy(), index=df.index)
    prev_day_low = pd.Series(day_low_prev.reindex(df.index.normalize()).to_numpy(), index=df.index)

    dist_prev_day_high = close - prev_day_high
    dist_prev_day_low = close - prev_day_low

    dist_high_std = dist_prev_day_high.rolling(100, min_periods=100).std()
    dist_low_std = dist_prev_day_low.rolling(100, min_periods=100).std()

    upper_wick = high - np.maximum(open_, close)
    lower_wick = np.minimum(open_, close) - low

    # Time
    hour = df.index.hour.to_numpy(dtype=float)
    dow = df.index.dayofweek.to_numpy(dtype=float)
    per_day_index = pd.Series(df.groupby(df.index.normalize()).cumcount(), index=df.index).astype(float)
    bars_in_day = pd.Series(df.groupby(df.index.normalize())["close"].transform("count"), index=df.index).astype(float)

    feats = pd.DataFrame(index=df.index)
    feats["hour_sin"] = np.sin(2.0 * np.pi * hour / 24.0)
    feats["hour_cos"] = np.cos(2.0 * np.pi * hour / 24.0)
    feats["dow_sin"] = np.sin(2.0 * np.pi * dow / 7.0)
    feats["dow_cos"] = np.cos(2.0 * np.pi * dow / 7.0)
    feats["bar_in_day_norm"] = per_day_index / (bars_in_day - 1.0 + EPS)

    feats["atr_ratio"] = atr14 / (atr100 + EPS)
    feats["vol_z20"] = (vol20 - vol20_mean) / (vol20_std + EPS)
    feats["compression_score"] = compression_score

    feats["ema50_slope_norm"] = ema50_slope / (close.abs() + EPS)
    feats["reg_slope_20"] = reg_slope_20
    feats["reg_r2_20"] = reg_r2_20

    feats["pos_in_range50"] = (close - rolling_low_50) / (rolling_high_50 - rolling_low_50 + EPS)
    feats["dist_prev_day_high_z"] = dist_prev_day_high / (dist_high_std + EPS)
    feats["dist_prev_day_low_z"] = dist_prev_day_low / (dist_low_std + EPS)
    feats["wick_body_ratio"] = (upper_wick + lower_wick) / (body + EPS)
    feats["body_range_ratio"] = body / (bar_range + EPS)
    feats["close_pos_in_bar"] = (close - low) / (bar_range + EPS)

    return feats


# backward compatibility
compute_normalized_features = compute_features
