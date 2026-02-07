from __future__ import annotations

import numpy as np
import pandas as pd


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([(df["high"] - df["low"]), (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=max(5, n // 2)).mean()


def label_tp_sl_first(
    df: pd.DataFrame,
    event_mask: pd.Series,
    tp_atr: float = 1.5,
    sl_atr: float = 1.0,
    horizon: int = 20,
    decision_time: str = "close",
) -> pd.DataFrame:
    if decision_time not in {"close", "open_next"}:
        raise ValueError("decision_time must be close|open_next")

    atr_t = _atr(df, 14)
    entry = df["close"].copy() if decision_time == "close" else df["open"].shift(-1)
    tp = entry + tp_atr * atr_t
    sl = entry - sl_atr * atr_t

    n = len(df)
    lab = np.full(n, np.nan)
    tp_hit = np.zeros(n, dtype=int)
    sl_hit = np.zeros(n, dtype=int)
    timeout = np.zeros(n, dtype=int)

    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    tpv = tp.to_numpy()
    slv = sl.to_numpy()
    ev = event_mask.fillna(False).to_numpy()

    for i in np.where(ev)[0]:
        start = i + 1 if decision_time == "close" else i + 2
        end = min(n - 1, i + horizon)
        if start > end:
            lab[i] = 0
            timeout[i] = 1
            continue
        decided = False
        for j in range(start, end + 1):
            t = highs[j] >= tpv[i]
            s = lows[j] <= slv[i]
            if t and not s:
                lab[i] = 1
                tp_hit[i] = 1
                decided = True
                break
            if s:
                lab[i] = 0
                sl_hit[i] = 1
                decided = True
                break
        if not decided:
            lab[i] = 0
            timeout[i] = 1

    return pd.DataFrame(
        {
            "label": lab,
            "entry_price": entry,
            "tp_price": tp,
            "sl_price": sl,
            "horizon_H": int(horizon),
            "tp_hit": tp_hit,
            "sl_hit": sl_hit,
            "timeout": timeout,
        },
        index=df.index,
    )
