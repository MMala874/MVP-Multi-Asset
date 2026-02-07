from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from features.indicators import atr


@dataclass(frozen=True)
class VolEventConfig:
    """Configuration constrained to the structural thesis requirements."""

    std_window: int = 20
    percentile_window_bars: int = 60 * 24 * 4  # 60 giorni su M15
    percentile_q: float = 0.20
    atr_fast: int = 14
    atr_slow: int = 100
    atr_ratio_threshold: float = 0.8
    mean_range_window: int = 5
    mean_range_atr_mult: float = 0.7
    expansion_lookahead_bars: int = 3
    expansion_range_mult: float = 1.5
    expansion_body_mult: float = 1.2


def compute_volatility_events(ohlc: pd.DataFrame, cfg: VolEventConfig | None = None) -> pd.DataFrame:
    """Compute thesis-defined compression/expansion events without extra features."""
    config = cfg or VolEventConfig()
    df = ohlc.copy()

    required = {"open", "high", "low", "close"}
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError(f"Missing required OHLC columns: {missing}")

    bar_range = df["high"] - df["low"]
    body = (df["close"] - df["open"]).abs()
    atr14 = atr(df, config.atr_fast)
    atr100 = atr(df, config.atr_slow)

    std20 = bar_range.rolling(config.std_window, min_periods=config.std_window).std()
    p20 = std20.rolling(config.percentile_window_bars, min_periods=config.percentile_window_bars).quantile(config.percentile_q)
    atr_ratio = atr14 / atr100.replace(0.0, np.nan)
    avg_range_5 = bar_range.rolling(config.mean_range_window, min_periods=config.mean_range_window).mean()

    compression = (std20 < p20) & (atr_ratio < config.atr_ratio_threshold) & (avg_range_5 < config.mean_range_atr_mult * atr14)
    compression = compression.fillna(False)
    compression_start = compression & (~compression.shift(1, fill_value=False))

    expansion_trigger = (bar_range > config.expansion_range_mult * atr14) | (body > config.expansion_body_mult * atr14)
    expansion_trigger = expansion_trigger.fillna(False)

    expansion_up = pd.Series(False, index=df.index)
    expansion_down = pd.Series(False, index=df.index)

    compression_idx = np.flatnonzero(compression_start.to_numpy())
    trigger_np = expansion_trigger.to_numpy()
    close_np = df["close"].to_numpy()
    open_np = df["open"].to_numpy()

    for idx in compression_idx:
        end = min(idx + config.expansion_lookahead_bars, len(df) - 1)
        if idx + 1 > end:
            continue
        window = trigger_np[idx + 1 : end + 1]
        hits = np.flatnonzero(window)
        if len(hits) == 0:
            continue
        exp_idx = idx + 1 + int(hits[0])
        if close_np[exp_idx] > open_np[exp_idx]:
            expansion_up.iloc[exp_idx] = True
        elif close_np[exp_idx] < open_np[exp_idx]:
            expansion_down.iloc[exp_idx] = True

    out = pd.DataFrame(
        {
            "compression_start": compression_start.astype(bool),
            "expansion_up": expansion_up.astype(bool),
            "expansion_down": expansion_down.astype(bool),
            "atr_14": atr14,
            "atr_100": atr100,
        },
        index=df.index,
    )
    return out
