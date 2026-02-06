from __future__ import annotations

import numpy as np
import pandas as pd

from features.indicators import atr, ema

EPS = 1e-12
BARS_PER_DAY_M15 = 96


def _rolling_percentile(series: pd.Series, window: int) -> pd.Series:
    def _percentile_last(values: np.ndarray) -> float:
        ranks = np.argsort(np.argsort(values))
        return float(ranks[-1]) / float(len(values) - 1)

    return series.rolling(window=window, min_periods=window).apply(_percentile_last, raw=True)


def _rolling_slope_and_r2(series: pd.Series, window: int) -> tuple[pd.Series, pd.Series]:
    x = np.arange(window, dtype=float)
    x_centered = x - x.mean()
    denom = (x_centered**2).sum()

    def _slope(values: np.ndarray) -> float:
        y_centered = values - values.mean()
        return (x_centered * y_centered).sum() / denom

    def _r2(values: np.ndarray) -> float:
        y_centered = values - values.mean()
        slope = (x_centered * y_centered).sum() / denom
        intercept = values.mean() - slope * x.mean()
        fitted = slope * x + intercept
        ss_res = ((values - fitted) ** 2).sum()
        ss_tot = ((values - values.mean()) ** 2).sum()
        if ss_tot <= EPS:
            return 0.0
        return 1.0 - (ss_res / ss_tot)

    slope_values = series.rolling(window=window, min_periods=window).apply(_slope, raw=True)
    r2_values = series.rolling(window=window, min_periods=window).apply(_r2, raw=True)
    return slope_values, r2_values


def _consecutive_direction_count(close: pd.Series, window: int = 5) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0.0)

    def _count(values: np.ndarray) -> float:
        tail_sign = values[-1]
        if tail_sign == 0:
            return 0.0
        count = 0
        for v in values[::-1]:
            if v == tail_sign:
                count += 1
            else:
                break
        return float(count)

    return direction.rolling(window=window, min_periods=window).apply(_count, raw=True)


def compute_normalized_features(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("Input dataframe index must be a DatetimeIndex")

    bar_range = df["high"] - df["low"]
    body = (df["close"] - df["open"]).abs()
    upper_wick = df["high"] - np.maximum(df["open"], df["close"])
    lower_wick = np.minimum(df["open"], df["close"]) - df["low"]

    atr_short = atr(df, 14)
    atr_long = atr(df, 100)
    returns = df["close"].pct_change()

    range_std_10 = bar_range.rolling(10, min_periods=10).std()
    lookback_30d = 30 * BARS_PER_DAY_M15

    realized_vol = returns.rolling(20, min_periods=20).std()
    realized_vol_mean = realized_vol.rolling(20, min_periods=20).mean()
    realized_vol_std = realized_vol.rolling(20, min_periods=20).std()

    ema50 = ema(df["close"], 50)
    ema50_mean = ema50.rolling(50, min_periods=50).mean()
    ema50_std = ema50.rolling(50, min_periods=50).std()

    reg_slope, reg_r2 = _rolling_slope_and_r2(df["close"], window=20)

    prev_day_high = df["high"].resample("1D").max().shift(1).reindex(df.index.normalize())
    prev_day_high = pd.Series(prev_day_high.to_numpy(), index=df.index)
    dist_prev_day_high = df["close"] - prev_day_high

    dist_prev_day_high_mean = dist_prev_day_high.rolling(50, min_periods=50).mean()
    dist_prev_day_high_std = dist_prev_day_high.rolling(50, min_periods=50).std()

    day_index = df.index.normalize()
    bar_idx_in_day = pd.Series(df.groupby(day_index).cumcount(), index=df.index, dtype=float)
    bars_per_day = pd.Series(df.groupby(day_index)["close"].transform("count"), index=df.index, dtype=float)

    contraction_count = (bar_range < bar_range.rolling(20, min_periods=20).mean()).rolling(5, min_periods=5).sum()

    features = pd.DataFrame(index=df.index)

    features["vol_atr_ratio"] = atr_short / (atr_long + EPS)
    features["vol_range_percentile_30d"] = _rolling_percentile(bar_range, lookback_30d)
    features["vol_realized_vol_z20"] = (realized_vol - realized_vol_mean) / (realized_vol_std + EPS)
    features["vol_compression_score"] = 1.0 - _rolling_percentile(range_std_10, lookback_30d)
    features["vol_expansion_ratio"] = bar_range / (bar_range.rolling(20, min_periods=20).mean() + EPS)

    ema50_slope = ema50.diff()
    features["trend_ema50_slope_norm"] = ema50_slope / (df["close"].abs() + EPS)
    features["trend_dist_ema50_z50"] = (ema50 - ema50_mean) / (ema50_std + EPS)
    features["trend_reg_slope_20"] = reg_slope / (df["close"].abs() + EPS)
    features["trend_reg_r2_20"] = reg_r2

    rolling_low_50 = df["low"].rolling(50, min_periods=50).min()
    rolling_high_50 = df["high"].rolling(50, min_periods=50).max()
    features["pos_range50_percentile"] = (df["close"] - rolling_low_50) / (rolling_high_50 - rolling_low_50 + EPS)
    features["pos_dist_prev_day_high_z"] = (dist_prev_day_high - dist_prev_day_high_mean) / (dist_prev_day_high_std + EPS)
    features["pos_wick_body_ratio"] = (upper_wick + lower_wick) / (body + EPS)
    features["pos_close_in_bar_01"] = (df["close"] - df["low"]) / (bar_range + EPS)

    hours = df.index.hour.to_numpy(dtype=float)
    features["time_hour_sin"] = np.sin(2.0 * np.pi * hours / 24.0)
    features["time_hour_cos"] = np.cos(2.0 * np.pi * hours / 24.0)
    features["time_bar_index_in_day_norm"] = bar_idx_in_day / (bars_per_day - 1.0 + EPS)

    features["micro_body_range_ratio"] = body / (bar_range + EPS)
    features["micro_consecutive_direction_count_5"] = _consecutive_direction_count(df["close"], window=5)
    features["micro_short_momentum_burst_3"] = returns.rolling(3, min_periods=3).sum()
    features["micro_vol_contraction_count_5"] = contraction_count

    return features
