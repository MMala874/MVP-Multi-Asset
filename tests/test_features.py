import time

import numpy as np
import pandas as pd

from features.indicators import adx, atr, ema, slope, zscore
from features.regime import atr_pct_zscore, compute_atr_pct


def test_no_lookahead():
    series = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
    t = 5

    ema_original = ema(series, 3).iat[t]
    slope_original = slope(series, 3).iat[t]
    zscore_original = zscore(series, 3).iat[t]

    series_modified = series.copy()
    series_modified.iloc[t + 1 :] = series_modified.iloc[t + 1 :] + 100

    ema_modified = ema(series_modified, 3).iat[t]
    slope_modified = slope(series_modified, 3).iat[t]
    zscore_modified = zscore(series_modified, 3).iat[t]

    assert np.isclose(ema_original, ema_modified, equal_nan=True)
    assert np.isclose(slope_original, slope_modified, equal_nan=True)
    assert np.isclose(zscore_original, zscore_modified, equal_nan=True)


def test_atr_basic():
    df = pd.DataFrame(
        {
            "high": [10, 11, 12],
            "low": [8, 9, 10],
            "close": [9, 10, 11],
        }
    )
    result = atr(df, 2)
    assert np.isnan(result.iat[0])
    assert result.iat[1] == 2
    assert result.iat[2] == 2


def _atr_reference(df: pd.DataFrame, n: int) -> pd.Series:
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
    tr = ranges.max(axis=1)
    atr_values = tr.rolling(window=n, min_periods=n).mean()
    for idx in range(n, len(tr)):
        if pd.isna(atr_values.iat[idx]):
            continue
        prev_atr = atr_values.iat[idx - 1]
        if pd.isna(prev_atr):
            continue
        atr_values.iat[idx] = (prev_atr * (n - 1) + tr.iat[idx]) / n
    return atr_values


def test_atr_matches_reference():
    df = pd.DataFrame(
        {
            "high": [10, 10.5, 11.2, 12.0, 11.5, 12.2],
            "low": [9.5, 9.7, 10.3, 10.9, 10.7, 11.4],
            "close": [10.0, 10.2, 11.0, 11.5, 11.0, 12.0],
        }
    )
    expected = _atr_reference(df, 3)
    result = atr(df, 3)
    assert np.allclose(result, expected, equal_nan=True, atol=1e-10)


def test_atr_pct_window_changes_values():
    df = pd.DataFrame(
        {
            "high": [10, 11, 12, 11, 13, 12],
            "low": [9, 9.5, 10, 9.8, 11, 10.5],
            "close": [9.5, 10.2, 11, 10.5, 12.2, 11.3],
        }
    )
    atr_pct_1 = compute_atr_pct(df, atr_n=1)
    atr_pct_3 = compute_atr_pct(df, atr_n=3)
    idx = 4
    assert not np.isclose(atr_pct_1.iat[idx], atr_pct_3.iat[idx], equal_nan=True)


def test_atr_pct_zscore_no_lookahead() -> None:
    atr_pct = pd.Series([0.5, 1.0, 0.8, 1.2, 1.5, 0.9, 1.1, 1.3, 1.4, 1.6], dtype=float)
    window = 5
    t = 6

    z_original = atr_pct_zscore(atr_pct, window=window).iat[t]

    modified = atr_pct.copy()
    modified.iloc[t + 1 :] = modified.iloc[t + 1 :] + 5.0

    z_modified = atr_pct_zscore(modified, window=window).iat[t]
    assert np.isclose(z_original, z_modified, equal_nan=True)


def test_adx_reasonable() -> None:
    df = pd.DataFrame(
        {
            "high": [10, 11, 12, 13, 12, 14, 15, 14.5, 15.5, 16],
            "low": [9, 9.5, 10.5, 11, 10.8, 12, 13, 13.5, 14, 15],
            "close": [9.5, 10.5, 11.5, 12.5, 11.7, 13.5, 14.2, 14.1, 15, 15.5],
        }
    )
    n = 3
    result = adx(df, n)
    assert result.iloc[: n - 1].isna().all()
    assert (result.iloc[n - 1 :] >= 0).all()
    assert (result.iloc[n - 1 :] <= 100).all()


def test_atr_adx_performance_sanity() -> None:
    rng = np.random.default_rng(42)
    size = 100_000
    base = rng.normal(100, 1, size).cumsum()
    high = base + rng.uniform(0.1, 1.0, size)
    low = base - rng.uniform(0.1, 1.0, size)
    close = base + rng.normal(0, 0.2, size)
    df = pd.DataFrame({"high": high, "low": low, "close": close})

    start = time.perf_counter()
    atr(df, 14)
    adx(df, 14)
    elapsed = time.perf_counter() - start
    assert elapsed < 2.5
