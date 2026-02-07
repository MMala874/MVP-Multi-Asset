from __future__ import annotations

import numpy as np
import pandas as pd

from edge_discovery.labeling import _atr


def _infer_pip_size(close: pd.Series) -> float:
    med = float(pd.to_numeric(close, errors="coerce").median())
    return 0.01 if med >= 20 else 0.0001


def compute_forward_paths(ohlc: pd.DataFrame, horizon: int) -> dict[str, pd.DataFrame]:
    high = pd.to_numeric(ohlc["high"], errors="coerce")
    low = pd.to_numeric(ohlc["low"], errors="coerce")
    close = pd.to_numeric(ohlc["close"], errors="coerce")

    fwd_max = pd.concat([high.shift(-k) for k in range(1, horizon + 1)], axis=1).max(axis=1)
    fwd_min = pd.concat([low.shift(-k) for k in range(1, horizon + 1)], axis=1).min(axis=1)
    fwd_close = close.shift(-horizon)

    return {
        f"fwd_max_high_{horizon}": fwd_max.to_frame(f"fwd_max_high_{horizon}"),
        f"fwd_min_low_{horizon}": fwd_min.to_frame(f"fwd_min_low_{horizon}"),
        f"fwd_close_{horizon}": fwd_close.to_frame(f"fwd_close_{horizon}"),
    }


def forward_returns(ohlc: pd.DataFrame, horizon: int) -> pd.Series:
    close = pd.to_numeric(ohlc["close"], errors="coerce")
    return (close.shift(-horizon) / close) - 1.0


def triple_barrier_expectancy(
    ohlc: pd.DataFrame,
    event_mask: pd.Series | np.ndarray,
    horizon: int,
    tp_atr: float,
    sl_atr: float,
    decision_time: str = "close",
    side: str = "long",
    slippage_pips: float = 0.0,
    spread_mode: str = "none",
    fixed_spread_pips: float = 0.7,
    pip_size: float | None = None,
) -> pd.DataFrame:
    if decision_time not in {"close", "open_next"}:
        raise ValueError("decision_time must be close|open_next")
    if side not in {"long", "short"}:
        raise ValueError("side must be long|short")

    atr_t = _atr(ohlc, 14)
    entry = ohlc["close"].copy() if decision_time == "close" else ohlc["open"].shift(-1)
    direction = 1.0 if side == "long" else -1.0
    tp = entry + direction * tp_atr * atr_t
    sl = entry - direction * sl_atr * atr_t

    n = len(ohlc)
    event_arr = pd.Series(event_mask, index=ohlc.index).fillna(False).to_numpy(dtype=bool)
    highs = pd.to_numeric(ohlc["high"], errors="coerce").to_numpy()
    lows = pd.to_numeric(ohlc["low"], errors="coerce").to_numpy()
    close = pd.to_numeric(ohlc["close"], errors="coerce")
    pip = _infer_pip_size(close) if pip_size is None else float(pip_size)

    spread_series = pd.Series(0.0, index=ohlc.index)
    if spread_mode == "column" and "spread" in ohlc.columns:
        spread_series = pd.to_numeric(ohlc["spread"], errors="coerce").fillna(0.0)
    elif spread_mode == "fixed" or (spread_mode == "column" and "spread" not in ohlc.columns):
        spread_series = pd.Series(float(fixed_spread_pips), index=ohlc.index)

    r_mult = np.full(n, np.nan)
    hit_type = np.array([None] * n, dtype=object)
    exit_bar = np.full(n, np.nan)
    cost_r = np.full(n, np.nan)

    ent = entry.to_numpy()
    tpv = tp.to_numpy()
    slv = sl.to_numpy()
    atrv = atr_t.to_numpy()
    spread_pips = spread_series.to_numpy()

    rr = tp_atr / sl_atr if sl_atr > 0 else np.nan
    for i in np.where(event_arr)[0]:
        start = i + 1 if decision_time == "close" else i + 2
        end = min(n - 1, i + horizon)
        if start > end or not np.isfinite(ent[i]) or not np.isfinite(atrv[i]) or atrv[i] <= 0:
            r_mult[i] = np.nan
            continue

        realized = 0.0
        kind = "TIMEOUT"
        ebar = end
        for j in range(start, end + 1):
            if side == "long":
                tp_hit = highs[j] >= tpv[i]
                sl_hit = lows[j] <= slv[i]
            else:
                tp_hit = lows[j] <= tpv[i]
                sl_hit = highs[j] >= slv[i]

            if tp_hit and not sl_hit:
                realized = float(rr)
                kind = "TP"
                ebar = j
                break
            if sl_hit:
                realized = -1.0
                kind = "SL"
                ebar = j
                break

        sl_dist_price = max(abs(slv[i] - ent[i]), 1e-12)
        total_cost_price = (spread_pips[i] + float(slippage_pips)) * pip
        c_r = float(total_cost_price / sl_dist_price)

        r_mult[i] = realized - c_r
        hit_type[i] = kind
        exit_bar[i] = float(ebar - i)
        cost_r[i] = c_r

    return pd.DataFrame(
        {
            "r_mult": r_mult,
            "hit_type": hit_type,
            "exit_bar": exit_bar,
            "entry_price": entry,
            "tp_price": tp,
            "sl_price": sl,
            "cost_r": cost_r,
        },
        index=ohlc.index,
    )
