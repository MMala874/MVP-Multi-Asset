from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

try:
    from scipy.spatial.distance import jensenshannon
    from scipy.stats import ks_2samp
except Exception:  # pragma: no cover
    jensenshannon = None
    ks_2samp = None


def _validate_labels(df: pd.DataFrame) -> pd.Series:
    if "label" not in df.columns:
        raise ValueError("Dataset must contain 'label' column")
    y = pd.to_numeric(df["label"], errors="coerce")
    y = y[y.isin([0, 1])].astype(int)
    if y.empty:
        raise ValueError("No valid binary labels (0/1) found")
    return y


def compute_expectancy_R(df: pd.DataFrame, tp_atr: float, sl_atr: float) -> dict[str, float | int]:
    y = _validate_labels(df)
    p_win = float(y.mean())
    e_r = float(p_win * tp_atr - (1.0 - p_win) * sl_atr)
    breakeven_p = float(sl_atr / (tp_atr + sl_atr))
    return {
        "p_win": p_win,
        "E_R": e_r,
        "breakeven_p": breakeven_p,
        "n": int(len(y)),
    }


def yearly_stability(df: pd.DataFrame, tp_atr: float, sl_atr: float) -> dict[str, Any]:
    if "year" in df.columns:
        years = pd.to_numeric(df["year"], errors="coerce")
    elif "timestamp" in df.columns:
        years = pd.to_datetime(df["timestamp"], utc=True, errors="coerce").dt.year
    else:
        raise ValueError("Dataset must contain 'year' or 'timestamp' for yearly stability")

    work = df.copy()
    work["year"] = years
    work = work.loc[work["year"].notna()].copy()

    table: dict[str, dict[str, float | int]] = {}
    neg = 0
    total = 0
    for year, grp in work.groupby("year"):
        stats = compute_expectancy_R(grp, tp_atr=tp_atr, sl_atr=sl_atr)
        table[str(int(year))] = {
            "p_win": float(stats["p_win"]),
            "E_R": float(stats["E_R"]),
            "n": int(stats["n"]),
        }
        total += 1
        if float(stats["E_R"]) <= 0.0:
            neg += 1

    neg_year_ratio = float(neg / total) if total > 0 else float("nan")
    return {"neg_year_ratio": neg_year_ratio, "year_table": table}


def _expectancy_from_labels(labels: np.ndarray, tp_atr: float, sl_atr: float) -> float:
    p = float(np.mean(labels))
    return float(p * tp_atr - (1.0 - p) * sl_atr)


def block_bootstrap_E(
    df: pd.DataFrame,
    tp_atr: float,
    sl_atr: float,
    B: int = 2000,
    block: int = 50,
    seed: int = 0,
) -> dict[str, float]:
    y = _validate_labels(df).to_numpy(dtype=int)
    n = len(y)
    if n == 0:
        return {"ci_low": np.nan, "ci_high": np.nan, "pvalue_E_le_0": np.nan}

    block = max(1, int(block))
    n_blocks = int(np.ceil(n / block))
    rng = np.random.default_rng(seed)
    boot_e = np.empty(B, dtype=float)

    starts_max = max(1, n - block + 1)
    for i in range(B):
        starts = rng.integers(0, starts_max, size=n_blocks)
        sample_parts = [y[s : min(s + block, n)] for s in starts]
        sample = np.concatenate(sample_parts)[:n]
        boot_e[i] = _expectancy_from_labels(sample, tp_atr=tp_atr, sl_atr=sl_atr)

    ci_low, ci_high = np.quantile(boot_e, [0.025, 0.975])
    pvalue_e_le_0 = float(np.mean(boot_e <= 0.0))
    return {
        "ci_low": float(ci_low),
        "ci_high": float(ci_high),
        "pvalue_E_le_0": pvalue_e_le_0,
    }


def permutation_test_labels(
    df: pd.DataFrame,
    tp_atr: float,
    sl_atr: float,
    B: int = 2000,
    seed: int = 0,
) -> dict[str, float]:
    if "year" in df.columns:
        years = pd.to_numeric(df["year"], errors="coerce")
    elif "timestamp" in df.columns:
        years = pd.to_datetime(df["timestamp"], utc=True, errors="coerce").dt.year
    else:
        raise ValueError("Dataset must contain 'year' or 'timestamp' for permutation test")

    y = _validate_labels(df)
    work = pd.DataFrame({"label": y, "year": years.loc[y.index]})
    work = work.loc[work["year"].notna()].copy()

    labels = work["label"].to_numpy(dtype=int)
    observed = _expectancy_from_labels(labels, tp_atr=tp_atr, sl_atr=sl_atr)

    rng = np.random.default_rng(seed)
    perm_vals = np.empty(B, dtype=float)
    year_values = work["year"].to_numpy()
    year_groups = [np.flatnonzero(year_values == yv) for yv in np.unique(year_values)]

    for i in range(B):
        perm = labels.copy()
        for idx in year_groups:
            perm[idx] = rng.permutation(perm[idx])
        perm_vals[i] = _expectancy_from_labels(perm, tp_atr=tp_atr, sl_atr=sl_atr)

    pvalue = float((np.sum(perm_vals >= observed) + 1) / (B + 1))
    return {"observed_E_R": float(observed), "pvalue": pvalue}


def _js_divergence(train: np.ndarray, holdout: np.ndarray, bins: int = 20) -> float:
    if jensenshannon is None:
        return float("nan")
    lo = float(min(np.min(train), np.min(holdout)))
    hi = float(max(np.max(train), np.max(holdout)))
    if not np.isfinite(lo) or not np.isfinite(hi) or lo == hi:
        return 0.0
    edges = np.linspace(lo, hi, bins + 1)
    h1, _ = np.histogram(train, bins=edges)
    h2, _ = np.histogram(holdout, bins=edges)
    p = h1.astype(float)
    q = h2.astype(float)
    p = p / (p.sum() + 1e-12)
    q = q / (q.sum() + 1e-12)
    return float(jensenshannon(p, q, base=2.0) ** 2)


def distribution_shift_tests(df: pd.DataFrame, feature_cols: list[str]) -> dict[str, Any]:
    if "split" not in df.columns:
        raise ValueError("distribution_shift_tests requires a 'split' column with values ['train', 'holdout']")
    if ks_2samp is None:
        raise ImportError("scipy is required for KS tests")

    train = df.loc[df["split"] == "train"]
    hold = df.loc[df["split"] == "holdout"]
    if train.empty or hold.empty:
        return {"features": {}, "pct_features_p001": np.nan, "n_features": 0}

    out: dict[str, dict[str, float]] = {}
    for c in feature_cols:
        if c not in train.columns or c not in hold.columns:
            continue
        a = pd.to_numeric(train[c], errors="coerce").dropna().to_numpy(dtype=float)
        b = pd.to_numeric(hold[c], errors="coerce").dropna().to_numpy(dtype=float)
        if len(a) < 5 or len(b) < 5:
            out[c] = {"ks_stat": np.nan, "ks_pvalue": np.nan, "js_div": np.nan}
            continue
        ks = ks_2samp(a, b, alternative="two-sided", method="auto")
        out[c] = {
            "ks_stat": float(ks.statistic),
            "ks_pvalue": float(ks.pvalue),
            "js_div": _js_divergence(a, b),
        }

    pvals = [v["ks_pvalue"] for v in out.values() if np.isfinite(v["ks_pvalue"])]
    pct_p001 = float(np.mean(np.array(pvals) < 0.01)) if pvals else float("nan")
    return {
        "features": out,
        "pct_features_p001": pct_p001,
        "n_features": len(out),
    }
