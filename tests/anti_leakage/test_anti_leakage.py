import pandas as pd
import numpy as np

from execution.fill_rules import get_fill_price
from features.indicators import atr, ema, slope, zscore
from features.regime import rolling_percentile
from backtest.trade_log import TRADE_LOG_COLUMNS
from validation.filter_tuner import _apply_filters


def test_feature_functions_ignore_future_data() -> None:
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

    df = pd.DataFrame(
        {
            "high": [10.0, 11.0, 12.0, 13.0],
            "low": [9.0, 10.0, 11.0, 12.0],
            "close": [9.5, 10.5, 11.5, 12.5],
        }
    )
    atr_original = atr(df, 2).iat[2]
    df_modified = df.copy()
    df_modified.loc[3, "high"] = 99.0
    df_modified.loc[3, "low"] = 1.0
    df_modified.loc[3, "close"] = 50.0
    atr_modified = atr(df_modified, 2).iat[2]
    assert np.isclose(atr_original, atr_modified, equal_nan=True)


def test_bar_contract_fill_is_open_next() -> None:
    df = pd.DataFrame({"open": [1.1, 1.2, 1.3]})
    assert get_fill_price(df, idx_t=0, side="buy") == 1.2


def test_rolling_percentile_uses_rolling_window() -> None:
    series = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
    window = 5
    t = 4

    original = rolling_percentile(series, window, 50).iat[t]

    modified = series.copy()
    modified.iloc[t + 1 :] = modified.iloc[t + 1 :] + 100

    recomputed = rolling_percentile(modified, window, 50).iat[t]
    assert np.isclose(original, recomputed, equal_nan=True)


def test_breakout_filter_uses_train_only_percentiles() -> None:
    df = pd.DataFrame(
        {
            "atr_pct": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
            "pnl": [0.1] * 8,
        }
    )
    train_idx = range(0, 4)
    val_idx = range(4, 6)
    params = {"atr_pct_percentile_low": 0.2, "atr_pct_percentile_high": 0.8, "spike_block": False}

    baseline = _apply_filters("S3_BREAKOUT_ATR_REGIME_EMA200", params, df, train_idx, val_idx)

    df_modified = df.copy()
    df_modified.loc[list(val_idx), "atr_pct"] = [500.0, 600.0]

    recomputed = _apply_filters("S3_BREAKOUT_ATR_REGIME_EMA200", params, df_modified, train_idx, val_idx)

    assert baseline["atr_pct"].tolist() == recomputed["atr_pct"].tolist()


def test_trade_log_tracks_feature_time_bounds() -> None:
    assert "features_max_time_used" in TRADE_LOG_COLUMNS

    trade_log = pd.DataFrame(
        [
            {
                "trade_id": 1,
                "order_id": "o-1",
                "symbol": "EURUSD",
                "strategy_id": "s1",
                "side": "long",
                "qty": 1.0,
                "signal_time": pd.Timestamp("2024-01-01T00:00:00Z"),
                "signal_idx": 0,
                "fill_time": pd.Timestamp("2024-01-01T00:05:00Z"),
                "entry_price": 1.0,
                "exit_time": pd.Timestamp("2024-01-01T00:10:00Z"),
                "exit_price": 1.1,
                "pnl": 0.1,
                "pnl_pct": 0.1,
                "spread_used": 0.0,
                "slippage_used": 0.0,
                "scenario": "A",
                "regime_snapshot": "LOW",
                "reason_codes": "",
                "features_max_time_used": pd.Timestamp("2024-01-01T00:00:00Z"),
            }
        ]
    )

    assert (trade_log["features_max_time_used"] <= trade_log["signal_time"]).all()
