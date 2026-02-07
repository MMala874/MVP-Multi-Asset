from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class OutcomeConfig:
    forward_horizons: tuple[int, ...] = (5, 10, 20)
    tail_q: float = 0.10


def _skew(values: pd.Series) -> float:
    x = values.dropna().to_numpy(dtype=float)
    if len(x) < 3:
        return float("nan")
    mean = x.mean()
    std = x.std(ddof=1)
    if std == 0.0:
        return 0.0
    centered = (x - mean) / std
    return float(np.mean(centered**3))


def build_event_outcomes(
    ohlc: pd.DataFrame,
    event_df: pd.DataFrame,
    regime_df: pd.DataFrame,
    cfg: OutcomeConfig | None = None,
) -> pd.DataFrame:
    """Create event-level forward outcomes with no TP/SL strategy logic."""
    config = cfg or OutcomeConfig()

    close = ohlc["close"]
    out = pd.DataFrame(index=ohlc.index)
    out["expansion_up"] = event_df["expansion_up"].astype(bool)
    out["expansion_down"] = event_df["expansion_down"].astype(bool)
    out["event"] = out["expansion_up"] | out["expansion_down"]
    out["event_direction"] = 0
    out.loc[out["expansion_up"], "event_direction"] = 1
    out.loc[out["expansion_down"], "event_direction"] = -1
    out["regime"] = regime_df["regime"]

    for horizon in config.forward_horizons:
        fwd = close.shift(-horizon) / close - 1.0
        signed_fwd = fwd * out["event_direction"]
        out[f"fwd_ret_{horizon}"] = fwd
        out[f"fwd_signed_ret_{horizon}"] = signed_fwd

    event_outcomes = out.loc[out["event"]].copy()
    event_outcomes["year"] = event_outcomes.index.year
    return event_outcomes


def summarize_outcomes_by_regime(
    event_outcomes: pd.DataFrame,
    unconditional_frame: pd.DataFrame,
    cfg: OutcomeConfig | None = None,
) -> pd.DataFrame:
    """Compute conditional expectation, skew, tail risk, and directional persistence ratio."""
    config = cfg or OutcomeConfig()

    rows: list[dict[str, float | str | int]] = []
    regimes = ["TREND_UP", "TREND_DOWN", "RANGE"]

    for regime in regimes:
        event_regime = event_outcomes.loc[event_outcomes["regime"] == regime]
        uncond_regime = unconditional_frame.loc[unconditional_frame["regime"] == regime]

        for horizon in config.forward_horizons:
            metric_col = f"fwd_signed_ret_{horizon}"
            event_values = event_regime[metric_col].dropna()
            uncond_values = uncond_regime[f"fwd_ret_{horizon}"].dropna()
            if event_values.empty:
                continue

            tail_thr = uncond_values.quantile(config.tail_q) if not uncond_values.empty else np.nan
            rows.append(
                {
                    "regime": regime,
                    "horizon": horizon,
                    "n_events": int(event_values.shape[0]),
                    "mean_forward_return": float(event_values.mean()),
                    "skew": _skew(event_values),
                    "pct_positive": float((event_values > 0).mean()),
                    "conditional_expectation": float(event_values.mean()),
                    "tail_probability": float((event_values <= tail_thr).mean()) if not np.isnan(tail_thr) else np.nan,
                    "directional_persistence_ratio": float((event_values > 0).mean()),
                }
            )

    return pd.DataFrame(rows)


def build_unconditional_frame(ohlc: pd.DataFrame, regime_df: pd.DataFrame, cfg: OutcomeConfig | None = None) -> pd.DataFrame:
    config = cfg or OutcomeConfig()
    close = ohlc["close"]

    out = pd.DataFrame(index=ohlc.index)
    out["regime"] = regime_df["regime"]
    for horizon in config.forward_horizons:
        out[f"fwd_ret_{horizon}"] = close.shift(-horizon) / close - 1.0
    out["year"] = out.index.year
    return out
