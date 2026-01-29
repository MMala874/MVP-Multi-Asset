import numpy as np
import pandas as pd

from features.indicators import atr, ema, slope, zscore
from features.regime import compute_atr_pct, rolling_percentile


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


def test_rolling_percentile_no_lookahead():
    series = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
    window = 5
    t = 4

    original = rolling_percentile(series, window, 50).iat[t]

    modified = series.copy()
    modified.iloc[t + 1 :] = modified.iloc[t + 1 :] + 100

    recomputed = rolling_percentile(modified, window, 50).iat[t]
    assert np.isclose(original, recomputed, equal_nan=True)


def test_rolling_percentile_no_lookahead_multiple_thresholds():
    atr_pct = pd.Series([0.5, 1.0, 0.8, 1.2, 1.5, 0.9, 1.1, 1.3, 1.4, 1.6], dtype=float)
    window = 5
    t = 6

    p35_original = rolling_percentile(atr_pct, window, 35).iat[t]
    p75_original = rolling_percentile(atr_pct, window, 75).iat[t]

    modified = atr_pct.copy()
    modified.iloc[t + 1 :] = modified.iloc[t + 1 :] + 5.0

    p35_modified = rolling_percentile(modified, window, 35).iat[t]
    p75_modified = rolling_percentile(modified, window, 75).iat[t]

    assert np.isclose(p35_original, p35_modified, equal_nan=True)
    assert np.isclose(p75_original, p75_modified, equal_nan=True)
