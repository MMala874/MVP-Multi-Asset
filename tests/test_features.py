import numpy as np
import pandas as pd

from features.indicators import atr, ema, slope, zscore
from features.regime import rolling_percentile


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


def test_rolling_percentile_no_lookahead():
    series = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
    window = 5
    t = 4

    original = rolling_percentile(series, window, 50).iat[t]

    modified = series.copy()
    modified.iloc[t + 1 :] = modified.iloc[t + 1 :] + 100

    recomputed = rolling_percentile(modified, window, 50).iat[t]
    assert np.isclose(original, recomputed, equal_nan=True)
