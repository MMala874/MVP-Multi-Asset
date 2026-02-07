from __future__ import annotations

import numpy as np
import pandas as pd


def _atr(df: pd.DataFrame, n: int) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([(df["high"] - df["low"]), (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=max(5, n // 2)).mean()


def _rolling_slope(s: pd.Series, n: int) -> pd.Series:
    x = np.arange(n, dtype=float)

    def _fit(y: np.ndarray) -> float:
        if np.isnan(y).any():
            return np.nan
        xm = x.mean()
        ym = y.mean()
        den = ((x - xm) ** 2).sum()
        if den == 0:
            return np.nan
        return float(((x - xm) * (y - ym)).sum() / den)

    return s.rolling(n, min_periods=n).apply(_fit, raw=True)


def _rolling_r2(s: pd.Series, n: int) -> pd.Series:
    x = np.arange(n, dtype=float)

    def _r2(y: np.ndarray) -> float:
        if np.isnan(y).any():
            return np.nan
        m, b = np.polyfit(x, y, 1)
        yhat = m * x + b
        ss_res = ((y - yhat) ** 2).sum()
        ss_tot = ((y - y.mean()) ** 2).sum()
        if ss_tot == 0:
            return 0.0
        return float(1.0 - (ss_res / ss_tot))

    return s.rolling(n, min_periods=n).apply(_r2, raw=True)


def build_causal_features(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    idx = df.index
    minute = idx.hour * 60 + idx.minute
    out["hour_sin"] = np.sin(2 * np.pi * idx.hour / 24.0)
    out["hour_cos"] = np.cos(2 * np.pi * idx.hour / 24.0)
    out["dow_sin"] = np.sin(2 * np.pi * idx.dayofweek / 7.0)
    out["dow_cos"] = np.cos(2 * np.pi * idx.dayofweek / 7.0)
    out["bar_in_day_norm"] = minute / (24 * 60)

    atr14 = _atr(df, 14)
    atr100 = _atr(df, 100)
    out["atr14"] = atr14
    out["atr100"] = atr100
    out["atr_ratio"] = atr14 / atr100.replace(0.0, np.nan)
    out["vol_z20"] = (atr14 - atr14.shift(1).rolling(20, min_periods=10).mean()) / atr14.shift(1).rolling(20, min_periods=10).std().replace(0.0, np.nan)

    rh = df["high"].shift(1).rolling(50, min_periods=20).max()
    rl = df["low"].shift(1).rolling(50, min_periods=20).min()
    out["pos_in_range50"] = (df["close"] - rl) / (rh - rl).replace(0.0, np.nan)

    day = idx.normalize()
    pdh = df["high"].resample("1D").max().shift(1)
    pdl = df["low"].resample("1D").min().shift(1)
    prev_day_high = pd.Series(pdh.reindex(day).to_numpy(), index=idx)
    prev_day_low = pd.Series(pdl.reindex(day).to_numpy(), index=idx)
    out["dist_prev_day_high_z"] = (df["close"] - prev_day_high) / atr14.replace(0.0, np.nan)
    out["dist_prev_day_low_z"] = (df["close"] - prev_day_low) / atr14.replace(0.0, np.nan)

    body = (df["close"] - df["open"]).abs()
    upper = df["high"] - df[["open", "close"]].max(axis=1)
    lower = df[["open", "close"]].min(axis=1) - df["low"]
    wick = upper + lower
    rng = (df["high"] - df["low"]).replace(0.0, np.nan)
    out["wick_body_ratio"] = wick / body.replace(0.0, np.nan)
    out["body_range_ratio"] = body / rng
    out["close_pos_in_bar"] = (df["close"] - df["low"]) / rng

    ema50 = df["close"].ewm(span=50, adjust=False).mean()
    out["ema50_slope_norm"] = (ema50 - ema50.shift(5)) / (5.0 * atr14.replace(0.0, np.nan))
    log_close = np.log(df["close"].replace(0.0, np.nan))
    out["reg_slope_20"] = _rolling_slope(log_close, 20)
    out["reg_r2_20"] = _rolling_r2(log_close, 20)
    return out
