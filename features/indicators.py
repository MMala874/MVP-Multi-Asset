import numpy as np
import pandas as pd


def ema(series: pd.Series, n: int) -> pd.Series:
    """Exponential moving average using backward-only data."""
    return series.ewm(span=n, adjust=False, min_periods=n).mean()


def _true_range(df: pd.DataFrame) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    ranges = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(df: pd.DataFrame, n: int) -> pd.Series:
    """Average True Range (Wilder) using OHLC data."""
    tr = _true_range(df)
    atr_values = tr.rolling(window=n, min_periods=n).mean()
    for idx in range(n, len(tr)):
        if pd.isna(atr_values.iat[idx]):
            continue
        prev_atr = atr_values.iat[idx - 1]
        if pd.isna(prev_atr):
            continue
        atr_values.iat[idx] = (prev_atr * (n - 1) + tr.iat[idx]) / n
    return atr_values


def adx(df: pd.DataFrame, n: int) -> pd.Series:
    """Average Directional Index (Wilder)."""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = _true_range(df)

    plus_dm = pd.Series(plus_dm, index=df.index)
    minus_dm = pd.Series(minus_dm, index=df.index)

    atr_series = atr(df, n)

    plus_dm_smoothed = plus_dm.rolling(window=n, min_periods=n).sum()
    minus_dm_smoothed = minus_dm.rolling(window=n, min_periods=n).sum()

    for idx in range(n, len(df)):
        if pd.isna(plus_dm_smoothed.iat[idx - 1]):
            continue
        plus_dm_smoothed.iat[idx] = plus_dm_smoothed.iat[idx - 1] - (
            plus_dm_smoothed.iat[idx - 1] / n
        ) + plus_dm.iat[idx]
        minus_dm_smoothed.iat[idx] = minus_dm_smoothed.iat[idx - 1] - (
            minus_dm_smoothed.iat[idx - 1] / n
        ) + minus_dm.iat[idx]

    plus_di = 100 * (plus_dm_smoothed / atr_series)
    minus_di = 100 * (minus_dm_smoothed / atr_series)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)

    adx_series = dx.rolling(window=n, min_periods=n).mean()
    for idx in range(n, len(df)):
        if pd.isna(adx_series.iat[idx - 1]):
            continue
        adx_series.iat[idx] = (adx_series.iat[idx - 1] * (n - 1) + dx.iat[idx]) / n

    return adx_series


def rolling_std_returns(close: pd.Series, n: int) -> pd.Series:
    returns = close.pct_change()
    return returns.rolling(window=n, min_periods=n).std()


def slope(series: pd.Series, n: int) -> pd.Series:
    x = np.arange(n)
    x_var = ((x - x.mean()) ** 2).sum()

    def _slope(window: np.ndarray) -> float:
        y = window
        return ((x - x.mean()) * (y - y.mean())).sum() / x_var

    return series.rolling(window=n, min_periods=n).apply(_slope, raw=True)


def zscore(series: pd.Series, n: int) -> pd.Series:
    mean = series.rolling(window=n, min_periods=n).mean()
    std = series.rolling(window=n, min_periods=n).std()
    return (series - mean) / std
