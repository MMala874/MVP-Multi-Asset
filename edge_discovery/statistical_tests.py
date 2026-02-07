from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class StatsConfig:
    bootstrap_samples: int = 2000
    permutation_samples: int = 2000
    random_seed: int = 42


def _t_stat(values: pd.Series) -> float:
    x = values.dropna().to_numpy(dtype=float)
    n = len(x)
    if n < 2:
        return float("nan")
    std = x.std(ddof=1)
    if std == 0.0:
        return float("nan")
    return float(np.sqrt(n) * x.mean() / std)


def bootstrap_ci_mean(values: pd.Series, n_samples: int, rng: np.random.Generator) -> tuple[float, float]:
    x = values.dropna().to_numpy(dtype=float)
    if len(x) == 0:
        return float("nan"), float("nan")
    idx = rng.integers(0, len(x), size=(n_samples, len(x)))
    means = x[idx].mean(axis=1)
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def permutation_test_mean_diff(
    a: pd.Series,
    b: pd.Series,
    n_samples: int,
    rng: np.random.Generator,
) -> float:
    x = a.dropna().to_numpy(dtype=float)
    y = b.dropna().to_numpy(dtype=float)
    if len(x) == 0 or len(y) == 0:
        return float("nan")

    observed = x.mean() - y.mean()
    combined = np.concatenate([x, y])
    n_x = len(x)

    count = 0
    for _ in range(n_samples):
        perm = rng.permutation(combined)
        stat = perm[:n_x].mean() - perm[n_x:].mean()
        if abs(stat) >= abs(observed):
            count += 1
    return float((count + 1) / (n_samples + 1))


def cohen_d(sample: pd.Series, baseline: pd.Series) -> float:
    x = sample.dropna().to_numpy(dtype=float)
    y = baseline.dropna().to_numpy(dtype=float)
    if len(x) < 2 or len(y) < 2:
        return float("nan")
    vx = x.var(ddof=1)
    vy = y.var(ddof=1)
    pooled = ((len(x) - 1) * vx + (len(y) - 1) * vy) / (len(x) + len(y) - 2)
    if pooled <= 0:
        return float("nan")
    return float((x.mean() - y.mean()) / np.sqrt(pooled))


def compute_statistical_report(
    event_outcomes: pd.DataFrame,
    unconditional_frame: pd.DataFrame,
    horizons: tuple[int, ...] = (5, 10, 20),
    cfg: StatsConfig | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return regime/horizon statistics and stability-per-year table."""
    config = cfg or StatsConfig()
    rng = np.random.default_rng(config.random_seed)

    rows: list[dict[str, float | str | int]] = []
    stability_rows: list[dict[str, float | str | int]] = []
    regimes = ["TREND_UP", "TREND_DOWN", "RANGE"]

    for regime in regimes:
        ev_regime = event_outcomes.loc[event_outcomes["regime"] == regime]
        unc_regime = unconditional_frame.loc[unconditional_frame["regime"] == regime]

        for horizon in horizons:
            sample = ev_regime[f"fwd_signed_ret_{horizon}"].dropna()
            baseline = unc_regime[f"fwd_ret_{horizon}"].dropna()
            if sample.empty:
                continue

            ci_low, ci_high = bootstrap_ci_mean(sample, config.bootstrap_samples, rng)
            p_value = permutation_test_mean_diff(sample, baseline, config.permutation_samples, rng)
            eff_size = cohen_d(sample, baseline)

            rows.append(
                {
                    "regime": regime,
                    "horizon": horizon,
                    "n_events": int(sample.shape[0]),
                    "mean_forward_return": float(sample.mean()),
                    "skew": float(sample.skew()),
                    "pct_positive": float((sample > 0).mean()),
                    "t_stat": _t_stat(sample),
                    "ci_low": ci_low,
                    "ci_high": ci_high,
                    "p_value": p_value,
                    "effect_size_vs_unconditional": eff_size,
                }
            )

            per_year = ev_regime[["year", f"fwd_signed_ret_{horizon}"]].dropna()
            if not per_year.empty:
                grouped = per_year.groupby("year")[f"fwd_signed_ret_{horizon}"]
                for year, values in grouped:
                    stability_rows.append(
                        {
                            "regime": regime,
                            "horizon": horizon,
                            "year": int(year),
                            "n_events": int(values.shape[0]),
                            "mean_forward_return": float(values.mean()),
                            "pct_positive": float((values > 0).mean()),
                        }
                    )

    return pd.DataFrame(rows), pd.DataFrame(stability_rows)


def assign_decision_flags(stats_df: pd.DataFrame, stability_df: pd.DataFrame) -> pd.DataFrame:
    if stats_df.empty:
        return stats_df

    out = stats_df.copy()
    flags = []
    for _, row in out.iterrows():
        stable = stability_df[
            (stability_df["regime"] == row["regime"]) & (stability_df["horizon"] == row["horizon"])
        ]
        stable_years = 0
        if not stable.empty:
            stable_years = int((stable["mean_forward_return"] > 0).sum())

        strong = (
            (row["p_value"] < 0.05)
            and (row["ci_low"] > 0)
            and (row["effect_size_vs_unconditional"] > 0.2)
            and (stable_years >= 2)
        )
        conditional = (row["p_value"] < 0.10) and (row["mean_forward_return"] > 0)

        if strong:
            flags.append("STRUCTURAL_EDGE_CONFIRMED")
        elif conditional:
            flags.append("CONDITIONAL_EDGE_ONLY")
        else:
            flags.append("NO_EDGE")

    out["decision_flag"] = flags
    return out
