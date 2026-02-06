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
    for h in horizons:
        # matrix with normalized forward returns for each t and each step j=1..h
        fwd_cols = [(close.shift(-j) - close) / (atr14 + EPS) for j in range(1, h + 1)]
        mat = pd.concat(fwd_cols, axis=1)
        arr = mat.to_numpy(dtype=float)

        out[f"fwd_ret_mean_{h}"] = np.nanmean(arr, axis=1)
        out[f"fwd_ret_median_{h}"] = np.nanmedian(arr, axis=1)
        out[f"fwd_vol_{h}"] = np.nanstd(arr, axis=1)
        out[f"fwd_skew_{h}"] = [np.nan if np.isnan(row).any() else _skew(row) for row in arr]
        out[f"fwd_cvar95_{h}"] = [np.nan if np.isnan(row).any() else _cvar95(row) for row in arr]

        out[f"fwd_tailprob_{h}_k05"] = np.nanmean(arr < -0.5, axis=1)
        out[f"fwd_tailprob_{h}_k10"] = np.nanmean(arr < -1.0, axis=1)
        out[f"fwd_mae_{h}"] = np.nanmin(arr, axis=1)
        out[f"fwd_mfe_{h}"] = np.nanmax(arr, axis=1)

    return out
