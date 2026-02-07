from __future__ import annotations

import numpy as np
import pandas as pd

from features.indicators import atr

EPS = 1e-12


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

    n = len(df)
    label = np.full(n, np.nan, dtype=float)
    bars_to = np.full(n, np.nan, dtype=float)
    outcome = np.full(n, "NONE", dtype=object)
    fwd_ret_10 = np.full(n, np.nan, dtype=float)
    mfe_10 = np.full(n, np.nan, dtype=float)
    mae_10 = np.full(n, np.nan, dtype=float)

    ev_idx = np.flatnonzero(event_mask.fillna(False).to_numpy(dtype=bool))
    for i in ev_idx:
        a = atr14[i]
        if not np.isfinite(a) or a <= 0:
            continue

        end = min(i + horizon, n - 1)
        if end <= i:
            continue

        tp = close[i] + tp_atr * a
        sl = close[i] - sl_atr * a

        window_high = high[i + 1 : end + 1]
        window_low = low[i + 1 : end + 1]

        if window_high.size:
            mfe_10[i] = (np.max(window_high) - close[i]) / (a + EPS)
        if window_low.size:
            mae_10[i] = (np.min(window_low) - close[i]) / (a + EPS)
        fwd_ret_10[i] = (close[end] - close[i]) / (a + EPS)

        for j in range(i + 1, end + 1):
            hit_tp = high[j] >= tp
            hit_sl = low[j] <= sl
            if hit_tp and hit_sl:
                bars_to[i] = j - i
                outcome[i] = "BOTH"
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
            "bars_to_resolution": pd.Series(bars_to, index=df.index, dtype="Int64"),
            "outcome_type": outcome,
            "fwd_ret_10": fwd_ret_10,
            "mfe_10_atr": mfe_10,
            "mae_10_atr": mae_10,
        },
        index=df.index,
    )


label_event_bars = apply_double_barrier_labels
