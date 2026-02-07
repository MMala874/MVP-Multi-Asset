from __future__ import annotations

import numpy as np
import pandas as pd


def build_purged_walk_forward_splits(
    index: pd.DatetimeIndex,
    train_years: int = 3,
    val_years: int = 1,
    holdout_last_years: int = 2,
    purge_bars: int = 30,
    embargo_bars: int = 30,
) -> dict:
    years = pd.Index(index.year)
    uniq_years = sorted(years.unique())
    if len(uniq_years) < (train_years + val_years + holdout_last_years):
        raise ValueError("Not enough years for requested split settings")

    holdout_years = set(uniq_years[-holdout_last_years:])
    holdout_idx = np.where(years.isin(list(holdout_years)))[0]
    dev_idx = np.where(~years.isin(list(holdout_years)))[0]
    dev_years = sorted(set(years[dev_idx]))

    folds = []
    for val_start in dev_years:
        train_start = val_start - train_years
        train_mask = (years >= train_start) & (years < val_start)
        val_mask = (years >= val_start) & (years < val_start + val_years)
        train = np.where(train_mask & ~years.isin(list(holdout_years)))[0]
        val = np.where(val_mask & ~years.isin(list(holdout_years)))[0]
        if len(train) == 0 or len(val) == 0:
            continue

        left = max(0, int(val.min()) - purge_bars)
        right = min(len(index) - 1, int(val.max()) + embargo_bars)
        train = train[(train < left) | (train > right)]
        if len(train) == 0:
            continue
        folds.append({"train_idx": train, "val_idx": val, "val_start_year": int(val_start)})

    if not folds:
        raise ValueError("No valid purged folds produced")

    return {
        "folds": folds,
        "holdout_idx": holdout_idx,
        "dev_idx": dev_idx,
        "purge_bars": int(purge_bars),
        "embargo_bars": int(embargo_bars),
    }
