from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.core.window.rolling import Rolling

from features.indicators import ema, slope
from strategies import s2_mr_zscore_ema_regime as s2


def test_s2_loop_avoids_rolling_apply(monkeypatch) -> None:
    rows = 50_000
    close = pd.Series(np.linspace(100.0, 200.0, rows))
    df = pd.DataFrame({"close": close})
    df["ema_base"] = ema(df["close"], 20)
    df["ema_slope"] = slope(df["ema_base"], 20)
    df["adx"] = 10.0

    config = {"z_window": 30, "z_entry": 1.0, "adx_max": 20.0, "slope_th": 0.1}

    def _raise_on_apply(*args, **kwargs):
        raise AssertionError("Rolling.apply should not be called inside the bar loop.")

    monkeypatch.setattr(Rolling, "apply", _raise_on_apply, raising=True)

    start_idx = 30
    for idx in range(start_idx, rows - 1):
        ctx = {
            "df": df,
            "idx": idx,
            "symbol": "EURUSD",
            "current_time": pd.Timestamp("2024-01-01"),
            "config": config,
        }
        s2.generate_signal(ctx)
