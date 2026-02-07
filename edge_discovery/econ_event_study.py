from __future__ import annotations

import math

import numpy as np
import pandas as pd

from edge_discovery.cv import build_purged_walk_forward_splits


def _block_bootstrap_mean(x: np.ndarray, n_boot: int = 1000, block: int = 50, rng_seed: int = 42) -> np.ndarray:
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


def run_econ_event_study(
    dataset: pd.DataFrame,
    r_col: str,
    horizon: int,
    block_length: int = 50,
    holdout_gate_r: float = 0.03,
    max_neg_year_ratio: float = 0.2,
    stress_cost_r: float = 0.0,
) -> dict:
    df = dataset.copy()
    idx = pd.to_datetime(df["timestamp"], utc=True, errors="coerce") if "timestamp" in df.columns else pd.to_datetime(df.index, utc=True, errors="coerce")
    df = df.loc[idx.notna()].copy()
    df.index = pd.DatetimeIndex(idx[idx.notna()], name="timestamp")

    r = pd.to_numeric(df[r_col], errors="coerce")
    split = build_purged_walk_forward_splits(
        df.index,
        train_years=3,
        val_years=1,
        holdout_last_years=2,
        purge_bars=horizon + 10,
        embargo_bars=horizon + 10,
    )

    fold_rows = []
    yearly_e = []
    for fold in split["folds"]:
        r_tr = r.iloc[fold["train_idx"]].dropna().to_numpy()
        r_val = r.iloc[fold["val_idx"]].dropna().to_numpy()
        e_train = float(r_tr.mean()) if len(r_tr) else np.nan
        e_val = float(r_val.mean()) if len(r_val) else np.nan
        lift = e_val - e_train
        bs_e_val = _block_bootstrap_mean(r_val, n_boot=500, block=block_length)
        bs_lift = bs_e_val - _block_bootstrap_mean(r_tr, n_boot=500, block=block_length, rng_seed=99)
        ci_l, ci_h = np.nanpercentile(bs_lift, [2.5, 97.5])
        fold_rows.append(
            {
                "year": fold["val_start_year"],
                "E_train": e_train,
                "E_val": e_val,
                "lift_R": float(lift),
                "lift_ci_low": float(ci_l),
                "lift_ci_high": float(ci_h),
            }
        )
        yearly_e.append((fold["val_start_year"], e_val))

    hold = r.iloc[split["holdout_idx"]].dropna().to_numpy()
    dev = r.iloc[split["dev_idx"]].dropna().to_numpy()
    e_train = float(dev.mean()) if len(dev) else np.nan
    e_hold = float(hold.mean()) if len(hold) else np.nan
    lift = e_hold - e_train

    bs_hold = _block_bootstrap_mean(hold, n_boot=2000, block=block_length)
    bs_train = _block_bootstrap_mean(dev, n_boot=2000, block=block_length, rng_seed=123)
    bs_lift = bs_hold - bs_train
    ci_hold = np.nanpercentile(bs_hold, [2.5, 97.5]).tolist()
    ci_lift = np.nanpercentile(bs_lift, [2.5, 97.5]).tolist()
    pvalue = float((bs_hold <= 0).mean())

    years = pd.Series(r.iloc[split["holdout_idx"]].values, index=df.index[split["holdout_idx"]]).groupby(lambda x: x.year).mean()
    neg_year_ratio = float((years <= 0).mean()) if len(years) else 1.0

    hold_stress = hold - stress_cost_r
    e_stress = float(np.nanmean(hold_stress)) if len(hold_stress) else np.nan

    reasons = []
    if not np.isfinite(e_hold) or e_hold < holdout_gate_r:
        reasons.append(f"E_holdout {e_hold:.4f} < {holdout_gate_r:.4f}")
    if not (ci_hold[0] > 0 or pvalue <= 0.05):
        reasons.append("holdout significance gate failed")
    if neg_year_ratio > max_neg_year_ratio:
        reasons.append(f"neg_year_ratio {neg_year_ratio:.2%} > {max_neg_year_ratio:.2%}")
    if not np.isfinite(e_stress) or e_stress < 0:
        reasons.append(f"E_stress {e_stress:.4f} < 0")

    return {
        "r_column": r_col,
        "folds": fold_rows,
        "holdout": {
            "E_train": e_train,
            "E_holdout": e_hold,
            "lift_R": float(lift),
            "CI_low": float(ci_hold[0]),
            "CI_high": float(ci_hold[1]),
            "lift_CI_low": float(ci_lift[0]),
            "lift_CI_high": float(ci_lift[1]),
            "pvalue": pvalue,
            "neg_year_ratio": neg_year_ratio,
            "E_stress": e_stress,
        },
        "decision": "ACCEPT" if not reasons else "REJECT",
        "reasons": reasons,
        "quarterly": {},
    }
