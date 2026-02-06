from __future__ import annotations

import numpy as np
import pandas as pd

from features.indicators import atr


def label_event_bars(
    df: pd.DataFrame,
    event_mask: pd.Series,
    tp_atr_mult: float = 1.2,
    sl_atr_mult: float = 1.0,
    max_horizon: int = 10,
) -> pd.DataFrame:
    """Apply a double-barrier label on event bars only.

    Labels are computed using only future bars up to ``max_horizon`` for each event row:
      1 -> TP hit first
      0 -> SL hit first
      NaN -> neither hit in horizon or ambiguous same-barrier hit.
    """
    atr14 = atr(df, 14)
    labels = pd.DataFrame(index=df.index, columns=["label", "bars_to_resolution", "outcome_type"], dtype=object)

    event_index = np.flatnonzero(event_mask.fillna(False).to_numpy())
    close = df["close"].to_numpy()
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    atr_values = atr14.to_numpy()

    for i in event_index:
        if np.isnan(atr_values[i]):
            labels.iat[i, 0] = np.nan
            labels.iat[i, 1] = np.nan
            labels.iat[i, 2] = "None"
            continue

        tp_level = close[i] + (tp_atr_mult * atr_values[i])
        sl_level = close[i] - (sl_atr_mult * atr_values[i])

        end = min(i + max_horizon, len(df) - 1)
        resolved = False
        for j in range(i + 1, end + 1):
            tp_hit = high[j] >= tp_level
            sl_hit = low[j] <= sl_level

            if tp_hit and sl_hit:
                labels.iat[i, 0] = np.nan
                labels.iat[i, 1] = j - i
                labels.iat[i, 2] = "None"
                resolved = True
                break
            if tp_hit:
                labels.iat[i, 0] = 1
                labels.iat[i, 1] = j - i
                labels.iat[i, 2] = "TP"
                resolved = True
                break
            if sl_hit:
                labels.iat[i, 0] = 0
                labels.iat[i, 1] = j - i
                labels.iat[i, 2] = "SL"
                resolved = True
                break

        if not resolved:
            labels.iat[i, 0] = np.nan
            labels.iat[i, 1] = np.nan
            labels.iat[i, 2] = "None"

    labels["label"] = pd.to_numeric(labels["label"], errors="coerce")
    labels["bars_to_resolution"] = pd.to_numeric(labels["bars_to_resolution"], errors="coerce")
    return labels
