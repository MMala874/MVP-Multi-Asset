from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from features.indicators import atr, ema


@dataclass(frozen=True)
class RegimeConfig:
    ema_period: int = 100
    slope_lookback: int = 10
    atr_fast: int = 14
    atr_slow: int = 100
    slope_trend_threshold: float = 0.05
    atr_range_ceiling: float = 0.9


def classify_vol_regime(ohlc: pd.DataFrame, cfg: RegimeConfig | None = None) -> pd.DataFrame:
    """Classify TREND_UP / TREND_DOWN / RANGE with thesis-constrained inputs only."""
    config = cfg or RegimeConfig()

    required = {"close", "high", "low"}
    missing = sorted(required.difference(ohlc.columns))
    if missing:
        raise ValueError(f"Missing required OHLC columns: {missing}")

    close = ohlc["close"]
    ema100 = ema(close, config.ema_period)
    atr14 = atr(ohlc, config.atr_fast)
    atr100 = atr(ohlc, config.atr_slow)

    slope_raw = (ema100 - ema100.shift(config.slope_lookback)) / float(config.slope_lookback)
    slope_norm = slope_raw / atr100.replace(0.0, np.nan)
    atr_ratio = atr14 / atr100.replace(0.0, np.nan)

    regime = pd.Series("RANGE", index=ohlc.index, dtype="object")
    up_mask = (slope_norm > config.slope_trend_threshold) & (atr_ratio >= config.atr_range_ceiling)
    down_mask = (slope_norm < -config.slope_trend_threshold) & (atr_ratio >= config.atr_range_ceiling)

    regime.loc[up_mask] = "TREND_UP"
    regime.loc[down_mask] = "TREND_DOWN"
    regime = regime.fillna("RANGE")

    return pd.DataFrame(
        {
            "ema100": ema100,
            "ema100_slope_norm": slope_norm,
            "atr_ratio_14_100": atr_ratio,
            "regime": regime,
        },
        index=ohlc.index,
    )
