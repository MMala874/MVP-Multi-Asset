from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Set

import numpy as np
import pandas as pd

from features.regime import atr_pct_zscore

from desk_types import Side, SignalIntent

STRATEGY_ID = "s3_breakout_atr_regime_ema200"


def required_features() -> Set[str]:
    return {"high", "low", "close", "atr", "ema200"}


def _get_param(config: Dict[str, Any], key: str, default: Any) -> Any:
    return config.get(key, default)


def generate_signal(ctx: Dict[str, Any]) -> SignalIntent:
    df: pd.DataFrame = ctx["df"]
    idx: int = ctx["idx"]
    symbol: str = ctx["symbol"]
    current_time: datetime = ctx["current_time"]
    config: Dict[str, Any] = ctx.get("config", {})

    high_col = _get_param(config, "high_col", "high")
    low_col = _get_param(config, "low_col", "low")
    close_col = _get_param(config, "close_col", "close")
    atr_col = _get_param(config, "atr_col", "atr")
    ema200_col = _get_param(config, "ema200_col", "ema200")

    compression_window = int(_get_param(config, "compression_window", 50))
    compression_z_low = float(_get_param(config, "compression_z_low", -0.5))
    breakout_window = int(_get_param(config, "breakout_window", 20))

    closes = df[close_col]
    highs = df[high_col]
    lows = df[low_col]
    atr_values = df[atr_col]
    ema200_value = df[ema200_col].iloc[idx]

    close_value = closes.iloc[idx]
    atr_value = atr_values.iloc[idx]

    tags: Dict[str, str] = {}

    atr_pct_series = atr_values / closes * 100
    atr_pct_value = atr_value / close_value * 100 if close_value != 0 else np.nan
    atr_pct_z = atr_pct_zscore(atr_pct_series, window=compression_window)
    compression_z = atr_pct_z.iloc[idx] if idx < len(atr_pct_z) else np.nan

    compression_pass = False
    if not pd.isna(compression_z) and not pd.isna(atr_pct_value):
        compression_pass = compression_z < compression_z_low

    tags["compression"] = "compression_pass" if compression_pass else "compression_fail"

    breakout_dir = "none"
    if idx >= breakout_window:
        range_high = highs.iloc[idx - breakout_window : idx].max()
        range_low = lows.iloc[idx - breakout_window : idx].min()
        if close_value > range_high:
            breakout_dir = "up"
        elif close_value < range_low:
            breakout_dir = "down"
    tags["breakout_dir"] = breakout_dir

    bias_pass = False
    if not pd.isna(ema200_value):
        if breakout_dir == "up" and close_value > ema200_value:
            bias_pass = True
        elif breakout_dir == "down" and close_value < ema200_value:
            bias_pass = True
    tags["bias"] = "bias_pass" if bias_pass else "bias_fail"

    side = Side.FLAT
    if compression_pass and bias_pass:
        if breakout_dir == "up":
            side = Side.LONG
        elif breakout_dir == "down":
            side = Side.SHORT

    return SignalIntent(
        strategy_id=STRATEGY_ID,
        symbol=symbol,
        side=side,
        signal_time=current_time,
        sl_points=None,
        tp_points=None,
        tags=tags,
    )
