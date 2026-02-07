from __future__ import annotations

import math

import numpy as np
import pandas as pd

from edge_discovery.cv import build_purged_walk_forward_splits


def _block_bootstrap_mean(x: np.ndarray, n_boot: int = 1000, block: int = 20, rng_seed: int = 42) -> np.ndarray:
    if len(x) == 0:
        return np.array([np.nan])
    rng = np.random.default_rng(rng_seed)
    out = np.empty(n_boot, dtype=float)
    k = int(math.ceil(len(x) / block))
    for b in range(n_boot):
        chunks = []
        for _ in range(k):
            s = rng.integers(0, max(1, len(x) - block + 1))
            chunks.append(x[s : s + block])
        out[b] = np.concatenate(chunks)[: len(x)].mean()
    return out


def _bh_fdr(pvals: list[float]) -> list[float]:
    m = len(pvals)
    order = np.argsort(np.array(pvals, dtype=float))
    adj = np.full(m, np.nan)
    run = 1.0
    for rank in range(m, 0, -1):
        idx = order[rank - 1]
        p = pvals[idx]
        if not np.isfinite(p):
            continue
        run = min(run, min(1.0, p * m / rank))
        adj[idx] = run
    return adj.tolist()


def run_event_study(dataset: pd.DataFrame, horizon: int, coverage: float, holdout_lift_gate: float = 0.08) -> dict:
    df = dataset.copy()
    idx = pd.to_datetime(df["timestamp"], utc=True, errors="coerce") if "timestamp" in df.columns else pd.to_datetime(df.index, utc=True, errors="coerce")
    df = df.loc[idx.notna()].copy()
    df.index = pd.DatetimeIndex(idx[idx.notna()], name="timestamp")
    y = pd.to_numeric(df["label"], errors="coerce").fillna(0).astype(int)

    split = build_purged_walk_forward_splits(
        df.index,
        train_years=3,
        val_years=1,
        holdout_last_years=2,
        purge_bars=horizon + 10,
        embargo_bars=horizon + 10,
    )

    fold_rows = []
    pvals = []
    for fold in split["folds"]:
        y_tr = y.iloc[fold["train_idx"]].to_numpy()
        y_val = y.iloc[fold["val_idx"]].to_numpy()
        base = float(y_tr.mean()) if len(y_tr) else np.nan
        ev = float(y_val.mean()) if len(y_val) else np.nan
        lift = ev - base
        bs = _block_bootstrap_mean(y_val, n_boot=500) - _block_bootstrap_mean(y_tr, n_boot=500, rng_seed=77)
        ci_l, ci_h = np.nanpercentile(bs, [2.5, 97.5])
        p = float((bs <= 0).mean())
        pvals.append(p)
        fold_rows.append(
            {
                "year": fold["val_start_year"],
                "baseline_pos_rate": base,
                "event_pos_rate": ev,
                "lift": lift,
                "lift_ci_low": float(ci_l),
                "lift_ci_high": float(ci_h),
                "pvalue": p,
            }
        )

    hold_y = y.iloc[split["holdout_idx"]].to_numpy()
    dev_y = y.iloc[split["dev_idx"]].to_numpy()
    hold_lift = float(hold_y.mean() - dev_y.mean())
    hold_bs = _block_bootstrap_mean(hold_y, n_boot=1000) - _block_bootstrap_mean(dev_y, n_boot=1000, rng_seed=99)
    hold_ci = np.nanpercentile(hold_bs, [2.5, 97.5]).tolist()
    hold_p = float((hold_bs <= 0).mean())
    pvals_all = pvals + [hold_p]
    adj = _bh_fdr(pvals_all)

    lifts = np.array([r["lift"] for r in fold_rows], dtype=float)
    neg_ratio = float((lifts < 0).mean()) if len(lifts) else 1.0
    stability = float((lifts > 0).mean()) if len(lifts) else 0.0

    reasons = []
    if hold_lift < holdout_lift_gate:
        reasons.append(f"holdout_lift {hold_lift:.4f} < {holdout_lift_gate:.4f}")
    if neg_ratio > 0.2:
        reasons.append(f"neg_year_ratio {neg_ratio:.2%} > 20%")
    if adj[-1] > 0.05:
        reasons.append(f"holdout pvalue_fdr {adj[-1]:.4f} > 0.05")

    return {
        "folds": fold_rows,
        "holdout": {
            "lift": hold_lift,
            "ci_low": float(hold_ci[0]),
            "ci_high": float(hold_ci[1]),
            "pvalue": hold_p,
            "pvalue_fdr": adj[-1],
        },
        "stability": {"pos_year_ratio": stability, "neg_year_ratio": neg_ratio},
        "decision": "ACCEPT_EDGE" if not reasons else "REJECT_EDGE",
        "reasons": reasons,
        "coverage": float(coverage),
    }
