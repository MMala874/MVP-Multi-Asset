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
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def adx(df: pd.DataFrame, n: int) -> pd.Series:
    """Average Directional Index (Wilder)."""
    high = df["high"]
    low = df["low"]

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    tr = _true_range(df)

    tr_smoothed = tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    plus_dm_smoothed = plus_dm.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    minus_dm_smoothed = minus_dm.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()

    plus_di = 100 * (plus_dm_smoothed / tr_smoothed)
    minus_di = 100 * (minus_dm_smoothed / tr_smoothed)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)

    return dx.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


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
