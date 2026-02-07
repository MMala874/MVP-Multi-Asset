from __future__ import annotations

import numpy as np
import pandas as pd

from features.indicators import atr


def apply_double_barrier_labels(
    df: pd.DataFrame,
    event_mask: pd.Series,
    tp_atr: float = 1.2,
    sl_atr: float = 1.0,
    horizon: int = 10,
) -> pd.DataFrame:
    atr14 = atr(df, 14).to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)

    label = np.full(len(df), np.nan, dtype=float)
    bars_to = np.full(len(df), np.nan, dtype=float)
    outcome = np.full(len(df), "NONE", dtype=object)

    ev_idx = np.flatnonzero(event_mask.fillna(False).to_numpy())
    for i in ev_idx:
        a = atr14[i]
        if not np.isfinite(a):
            continue
        tp = close[i] + tp_atr * a
        sl = close[i] - sl_atr * a
        end = min(i + horizon, len(df) - 1)
        for j in range(i + 1, end + 1):
            hit_tp = high[j] >= tp
            hit_sl = low[j] <= sl
            if hit_tp and hit_sl:
                bars_to[i] = j - i
                outcome[i] = "NONE"
                break
            if hit_tp:
                label[i] = 1.0
                bars_to[i] = j - i
                outcome[i] = "TP"
                break
            if hit_sl:
                label[i] = 0.0
                bars_to[i] = j - i
                outcome[i] = "SL"
                break

    return pd.DataFrame(
        {
            "label": label,
            "bars_to_resolution": pd.Series(bars_to).astype("Int64"),
            "outcome_type": outcome,
        },
        index=df.index,
    )


label_event_bars = apply_double_barrier_labels
