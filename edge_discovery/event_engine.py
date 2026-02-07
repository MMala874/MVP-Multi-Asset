from __future__ import annotations

import numpy as np
import pandas as pd

EPS = 1e-12


def compute_event_flags(df: pd.DataFrame, **_: float) -> pd.DataFrame:
    """Compute the single structural event flag SWEEP_RECLAIM_EXPAND.

    Requires OHLC and previous-day levels in columns `prev_day_high`/`prev_day_low`.
    If previous-day columns are missing, they are computed from OHLC with a 1-day shift.
    """
    data = df.copy()
    if "prev_day_high" not in data.columns or "prev_day_low" not in data.columns:
        day = data.index.normalize()
        prev_day_high = data["high"].resample("1D").max().shift(1)
        prev_day_low = data["low"].resample("1D").min().shift(1)
        data["prev_day_high"] = pd.Series(prev_day_high.reindex(day).to_numpy(), index=data.index)
        data["prev_day_low"] = pd.Series(prev_day_low.reindex(day).to_numpy(), index=data.index)

    sweep_high = (data["high"] > data["prev_day_high"]) & (data["close"] < data["prev_day_high"])
    sweep_low = (data["low"] < data["prev_day_low"]) & (data["close"] > data["prev_day_low"])
    event_sweep = sweep_high | sweep_low

    bar_range = (data["high"] - data["low"]).astype(float)
    baseline_range = bar_range.rolling(96, min_periods=96).median()
    expansion = (bar_range / (baseline_range + EPS)) >= 1.6

    out = pd.DataFrame(index=data.index)
    out["SWEEP_RECLAIM_EXPAND"] = (event_sweep & expansion & np.isfinite(baseline_range)).astype(int)
    return out
