from __future__ import annotations

import numpy as np
import pandas as pd

from features.indicators import atr

EPS = 1e-12


def _skew(values: np.ndarray) -> float:
    m = values.mean()
    s = values.std(ddof=0)
    if s <= EPS:
        return 0.0
    z = (values - m) / s
    return float((z**3).mean())


def _cvar95(values: np.ndarray) -> float:
    q = np.quantile(values, 0.05)
    tail = values[values <= q]
    if tail.size == 0:
        return float(q)
    return float(tail.mean())


def compute_forward_metrics(df: pd.DataFrame, horizons: list[int] | tuple[int, ...] = (5, 10, 20)) -> pd.DataFrame:
    """Compute forward distribution metrics using t+1..t+h only."""
    close = df["close"]
    atr14 = atr(df, 14)

    out = pd.DataFrame(index=df.index)
    n_rows = len(df)

    for h in horizons:
        fwd_cols = [(close.shift(-j) - close) / (atr14 + EPS) for j in range(1, h + 1)]
        mat = pd.concat(fwd_cols, axis=1)
        arr = mat.to_numpy(dtype=float)

        valid_horizon = (np.arange(n_rows) + h) < n_rows
        valid_idx = np.flatnonzero(valid_horizon)
        arr_valid = arr[valid_horizon]

        finite_mask = np.isfinite(arr_valid)
        nonempty_rows = finite_mask.any(axis=1)
        all_finite_rows = finite_mask.all(axis=1)

        mean = np.full(n_rows, np.nan, dtype=float)
        median = np.full(n_rows, np.nan, dtype=float)
        vol = np.full(n_rows, np.nan, dtype=float)
        tail_k05 = np.full(n_rows, np.nan, dtype=float)
        tail_k10 = np.full(n_rows, np.nan, dtype=float)
        mae = np.full(n_rows, np.nan, dtype=float)
        mfe = np.full(n_rows, np.nan, dtype=float)
        skew = np.full(n_rows, np.nan, dtype=float)
        cvar = np.full(n_rows, np.nan, dtype=float)

        if nonempty_rows.any():
            ne_idx = valid_idx[nonempty_rows]
            arr_nonempty = arr_valid[nonempty_rows]
            mean[ne_idx] = np.nanmean(arr_nonempty, axis=1)
            median[ne_idx] = np.nanmedian(arr_nonempty, axis=1)
            vol[ne_idx] = np.nanstd(arr_nonempty, axis=1)
            tail_k05[ne_idx] = np.nanmean(arr_nonempty < -0.5, axis=1)
            tail_k10[ne_idx] = np.nanmean(arr_nonempty < -1.0, axis=1)
            mae[ne_idx] = np.nanmin(arr_nonempty, axis=1)
            mfe[ne_idx] = np.nanmax(arr_nonempty, axis=1)

        if all_finite_rows.any():
            af_idx = valid_idx[all_finite_rows]
            arr_all_finite = arr_valid[all_finite_rows]
            skew[af_idx] = np.array([_skew(row) for row in arr_all_finite], dtype=float)
            cvar[af_idx] = np.array([_cvar95(row) for row in arr_all_finite], dtype=float)

        out[f"fwd_ret_mean_{h}"] = mean
        out[f"fwd_ret_median_{h}"] = median
        out[f"fwd_vol_{h}"] = vol
        out[f"fwd_skew_{h}"] = skew
        out[f"fwd_cvar95_{h}"] = cvar
        out[f"fwd_tailprob_{h}_k05"] = tail_k05
        out[f"fwd_tailprob_{h}_k10"] = tail_k10
        out[f"fwd_mae_{h}"] = mae
        out[f"fwd_mfe_{h}"] = mfe

    return out
