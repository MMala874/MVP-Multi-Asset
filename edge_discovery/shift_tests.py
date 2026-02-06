from __future__ import annotations

import re

import numpy as np
import pandas as pd


def permutation_test(
    a: np.ndarray,
    b: np.ndarray,
    metric: str = "mean",
    n_perm: int = 2000,
    seed: int = 42,
) -> dict[str, float]:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    a = a[~np.isnan(a)]
    b = b[~np.isnan(b)]
    if a.size == 0 or b.size == 0:
        return {"delta": np.nan, "ratio": np.nan, "pvalue_perm": np.nan}

    if metric == "mean":
        stat = lambda x: float(np.mean(x))
    elif metric == "median":
        stat = lambda x: float(np.median(x))
    else:
        raise ValueError("metric must be 'mean' or 'median'")

    obs_delta = stat(a) - stat(b)
    obs_ratio = stat(a) / (abs(stat(b)) + 1e-12)

    pooled = np.concatenate([a, b])
    n_a = a.size
    rng = np.random.default_rng(seed)

    exceed = 0
    for _ in range(n_perm):
        perm = rng.permutation(pooled)
        d = stat(perm[:n_a]) - stat(perm[n_a:])
        exceed += int(abs(d) >= abs(obs_delta))

    pvalue = (exceed + 1) / (n_perm + 1)
    return {"delta": obs_delta, "ratio": obs_ratio, "pvalue_perm": float(pvalue)}


def bootstrap_ci_delta(a: np.ndarray, b: np.ndarray, n_boot: int = 1000, seed: int = 42) -> tuple[float, float]:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    a = a[~np.isnan(a)]
    b = b[~np.isnan(b)]
    if a.size == 0 or b.size == 0:
        return (np.nan, np.nan)

    rng = np.random.default_rng(seed)
    deltas = np.empty(n_boot, dtype=float)
    for i in range(n_boot):
        sa = a[rng.integers(0, a.size, a.size)]
        sb = b[rng.integers(0, b.size, b.size)]
        deltas[i] = float(np.mean(sa) - np.mean(sb))

    lo, hi = np.quantile(deltas, [0.025, 0.975])
    return (float(lo), float(hi))


def extract_horizon(metric_col: str) -> int:
    m = re.search(r"_(\d+)(?:_|$)", metric_col)
    if not m:
        raise ValueError(f"Cannot infer horizon from metric: {metric_col}")
    return int(m.group(1))


def build_base_mask(event_series: pd.Series, horizon: int) -> pd.Series:
    base = event_series.eq(0).copy()
    event_idx = np.flatnonzero(event_series.to_numpy(dtype=int) == 1)
    if event_idx.size == 0:
        return base

    blocked = np.zeros(len(base), dtype=bool)
    for idx in event_idx:
        left = max(0, idx - horizon)
        right = min(len(base), idx + horizon + 1)
        blocked[left:right] = True

    return base & (~pd.Series(blocked, index=event_series.index))


def compare_event_vs_base(
    df: pd.DataFrame,
    event_col: str,
    metric_col: str,
    n_perm: int = 2000,
    seed: int = 42,
) -> dict:
    horizon = extract_horizon(metric_col)
    event = df[event_col].astype(int)
    base_mask = build_base_mask(event, horizon)

    group_event = df.loc[event == 1, metric_col].to_numpy(dtype=float)
    group_base = df.loc[base_mask, metric_col].to_numpy(dtype=float)

    perm = permutation_test(group_event, group_base, metric="mean", n_perm=n_perm, seed=seed)
    ci_lo, ci_hi = bootstrap_ci_delta(group_event, group_base, seed=seed)

    return {
        "event": event_col,
        "metric": metric_col,
        "horizon": horizon,
        "n_event": int(np.sum(~np.isnan(group_event))),
        "n_base": int(np.sum(~np.isnan(group_base))),
        "effect_delta": perm["delta"],
        "effect_ratio": perm["ratio"],
        "pvalue_perm": perm["pvalue_perm"],
        "ci_low": ci_lo,
        "ci_high": ci_hi,
        "coverage": float((event == 1).mean()),
    }
