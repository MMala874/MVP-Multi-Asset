from __future__ import annotations

import numpy as np
import pandas as pd


def bootstrap_ci(
    series: pd.Series,
    metric: str = "mean",
    n_bootstrap: int = 2000,
    ci: float = 0.95,
    seed: int = 42,
) -> dict[str, float]:
    """Bootstrap confidence interval for mean/median/sum of a return series."""
    if series.empty:
        raise ValueError("series cannot be empty")
    if not 0 < ci < 1:
        raise ValueError("ci must be in (0,1)")
    if n_bootstrap <= 0:
        raise ValueError("n_bootstrap must be positive")

    values = series.astype(float).to_numpy()
    rng = np.random.default_rng(seed)

    stats = np.empty(n_bootstrap, dtype=float)
    for i in range(n_bootstrap):
        sample = rng.choice(values, size=len(values), replace=True)
        if metric == "mean":
            stats[i] = sample.mean()
        elif metric == "median":
            stats[i] = float(np.median(sample))
        elif metric == "sum":
            stats[i] = sample.sum()
        else:
            raise ValueError(f"Unsupported metric: {metric}")

    alpha = 1 - ci
    lo, hi = np.quantile(stats, [alpha / 2, 1 - alpha / 2])
    return {
        "metric": metric,
        "point_estimate": float(getattr(series, metric)() if metric != "sum" else series.sum()),
        "ci_low": float(lo),
        "ci_high": float(hi),
        "ci": ci,
    }
