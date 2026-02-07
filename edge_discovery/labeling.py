from __future__ import annotations

import numpy as np
import pandas as pd


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([(df["high"] - df["low"]), (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(int(n)).mean()


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


def label_range_expansion(
    df: pd.DataFrame,
    event_mask: pd.Series,
    horizon: int = 20,
    range_k: float = 2.0,
    atr_len: int = 14,
) -> pd.Series:
    atr_t = _atr(df, int(atr_len))
    n = len(df)
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    ev = event_mask.fillna(False).to_numpy()

    labels = np.full(n, np.nan)
    threshold = (range_k * atr_t).to_numpy()

    h = max(int(horizon), 1)
    for i in np.where(ev)[0]:
        start = i + 1
        end = min(n - 1, i + h)
        if start > end:
            continue
        fmax = highs[start : end + 1].max()
        fmin = lows[start : end + 1].min()
        frng = float(fmax - fmin)
        thr = threshold[i]
        if np.isnan(thr):
            continue
        labels[i] = 1 if frng >= thr else 0

    return pd.Series(labels, index=df.index, name="label")


def label_directional_expansion(
    df: pd.DataFrame,
    event_mask: pd.Series,
    horizon: int = 20,
    dir_k: float = 1.0,
    atr_len: int = 14,
) -> pd.DataFrame:
    atr_t = _atr(df, int(atr_len))
    n = len(df)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    ev = event_mask.fillna(False).to_numpy(dtype=bool)

    labels = np.full(n, np.nan)
    up_move = np.full(n, np.nan)
    down_move = np.full(n, np.nan)
    threshold = (float(dir_k) * atr_t).to_numpy()

    h = max(int(horizon), 1)
    for i in np.flatnonzero(ev):
        start = i + 1
        end = min(n - 1, i + h)
        if start > end:
            continue

        entry = closes[i]
        up = float(np.max(highs[start : end + 1]) - entry)
        down = float(entry - np.min(lows[start : end + 1]))
        thr = threshold[i]

        up_move[i] = up
        down_move[i] = down

        if np.isnan(thr):
            continue
        if up - down >= thr:
            labels[i] = 1.0
        elif down - up >= thr:
            labels[i] = 0.0

    return pd.DataFrame(
        {
            "label": labels,
            "diag_up_move": up_move,
            "diag_down_move": down_move,
            "diag_thr": threshold,
        },
        index=df.index,
    )
