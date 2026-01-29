from __future__ import annotations

from datetime import datetime
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

from desk_types import Side

_BASE_DIR = Path(__file__).resolve().parents[1]


def _load_strategy(name: str):
    path = _BASE_DIR / "strategies" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


S1 = _load_strategy("s1_trend_ema_atr_adx")
S2 = _load_strategy("s2_mr_zscore_ema_regime")
S3 = _load_strategy("s3_breakout_atr_regime_ema200")


def _sample_time() -> datetime:
    return datetime(2024, 2, 3, 4, 5, 6)


def _make_base_df(rows: int = 60) -> pd.DataFrame:
    close = pd.Series(np.linspace(100, 130, rows))
    high = close + 1.5
    low = close - 1.5
    df = pd.DataFrame({"close": close, "high": high, "low": low})
    df["ema_fast"] = close.ewm(span=5, adjust=False).mean()
    df["ema_slow"] = close.ewm(span=10, adjust=False).mean()
    df["atr"] = 1.2
    df["adx"] = 25.0
    df["ema_base"] = close.ewm(span=20, adjust=False).mean()
    df["ema200"] = close.ewm(span=200, adjust=False).mean()
    return df


def _ctx(df: pd.DataFrame, idx: int, config: dict) -> dict:
    return {
        "df": df,
        "idx": idx,
        "symbol": "EURUSD",
        "current_time": _sample_time(),
        "config": config,
        "regime": {},
    }


def test_strategies_no_t_plus_1():
    idx = 30
    base_df = _make_base_df()

    s1_config = {"adx_th": 20.0, "k_sl": 2.0}
    s2_config = {
        "z_window": 10,
        "slope_window": 5,
        "z_entry": 1.0,
        "adx_max": 30.0,
        "slope_th": 0.1,
    }
    s3_config = {"compression_window": 10, "p_low": 20.0, "breakout_window": 5}

    s1_signal = S1.generate_signal(_ctx(base_df, idx, s1_config))
    s2_signal = S2.generate_signal(_ctx(base_df, idx, s2_config))
    s3_signal = S3.generate_signal(_ctx(base_df, idx, s3_config))

    future_df = base_df.copy()
    future_df.loc[idx + 1 :, "close"] = 999.0
    future_df.loc[idx + 1 :, "high"] = 1000.0
    future_df.loc[idx + 1 :, "low"] = 998.0
    future_df.loc[idx + 1 :, "ema_fast"] = 999.0
    future_df.loc[idx + 1 :, "ema_slow"] = 999.0
    future_df.loc[idx + 1 :, "ema_base"] = 999.0
    future_df.loc[idx + 1 :, "ema200"] = 999.0
    future_df.loc[idx + 1 :, "atr"] = 9.0
    future_df.loc[idx + 1 :, "adx"] = 99.0

    assert s1_signal == S1.generate_signal(_ctx(future_df, idx, s1_config))
    assert s2_signal == S2.generate_signal(_ctx(future_df, idx, s2_config))
    assert s3_signal == S3.generate_signal(_ctx(future_df, idx, s3_config))


def test_tags_present():
    rows = 40
    close = pd.Series([100.0] * (rows - 1) + [120.0])
    high = close + 1.0
    low = close - 1.0

    df = pd.DataFrame({"close": close, "high": high, "low": low})
    df["ema_fast"] = close.ewm(span=3, adjust=False).mean()
    df["ema_slow"] = close.ewm(span=8, adjust=False).mean()
    df["atr"] = [1.5] * rows
    df["adx"] = [15.0] * rows
    df["ema_base"] = [100.0] * rows
    df["ema200"] = [90.0] * rows

    idx = rows - 1

    s1_config = {"adx_th": 10.0, "k_sl": 1.5}
    s1_signal = S1.generate_signal(_ctx(df, idx, s1_config))
    assert s1_signal.side != Side.FLAT
    assert s1_signal.tags

    s2_config = {
        "z_window": 20,
        "slope_window": 5,
        "z_entry": 1.0,
        "adx_max": 20.0,
        "slope_th": 0.01,
    }
    s2_signal = S2.generate_signal(_ctx(df, idx, s2_config))
    assert s2_signal.side != Side.FLAT
    assert s2_signal.tags

    df_breakout = df.copy()
    df_breakout.loc[idx - 5 : idx - 1, "high"] = 101.0
    df_breakout.loc[idx - 5 : idx - 1, "low"] = 99.0
    df_breakout.loc[idx, "close"] = 105.0
    df_breakout.loc[idx, "high"] = 106.0
    df_breakout.loc[idx, "low"] = 104.0
    df_breakout.loc[: idx - 1, "atr"] = 2.0
    df_breakout.loc[idx, "atr"] = 0.5

    s3_config = {"compression_window": 10, "p_low": 30.0, "breakout_window": 5}
    s3_signal = S3.generate_signal(_ctx(df_breakout, idx, s3_config))
    assert s3_signal.side != Side.FLAT
    assert s3_signal.tags
