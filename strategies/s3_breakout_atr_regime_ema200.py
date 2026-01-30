from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Set

import numpy as np

from desk_types import Side, SignalIntent

STRATEGY_ID = "s3_breakout_atr_regime_ema200"


def required_features() -> Set[str]:
    return {
        "high",
        "low",
        "close",
        "atr",
        "ema200",
        "compression_z",
        "breakout_high",
        "breakout_low",
    }


def _get_param(config: Dict[str, Any], key: str, default: Any) -> Any:
    return config.get(key, default)


def _read_value(values: np.ndarray, idx: int) -> Optional[float]:
    value = values[idx]
    if value is None:
        return None
    if isinstance(value, (float, np.floating)) and np.isnan(value):
        return None
    return float(value)


def generate_signal(ctx: Dict[str, Any]) -> SignalIntent:
    cols: Dict[str, np.ndarray] = ctx["cols"]
    idx: int = ctx["idx"]
    symbol: str = ctx["symbol"]
    current_time: datetime = ctx["current_time"]
    config: Dict[str, Any] = ctx.get("config", {})

    high_col = _get_param(config, "high_col", "high")
    low_col = _get_param(config, "low_col", "low")
    close_col = _get_param(config, "close_col", "close")
    atr_col = _get_param(config, "atr_col", "atr")
    ema200_col = _get_param(config, "ema200_col", "ema200")
    compression_z_col = _get_param(config, "compression_z_col", "compression_z")
    breakout_high_col = _get_param(config, "breakout_high_col", "breakout_high")
    breakout_low_col = _get_param(config, "breakout_low_col", "breakout_low")

    compression_z_low = float(_get_param(config, "compression_z_low", -0.5))
    closes = cols[close_col]
    highs = cols[high_col]
    lows = cols[low_col]
    atr_values = cols[atr_col]
    ema200_value = _read_value(cols[ema200_col], idx)

    close_value = _read_value(closes, idx)
    atr_value = _read_value(atr_values, idx)

    tags: Dict[str, str] = {}

    if close_value is None or atr_value is None or close_value == 0:
        atr_pct_value = None
    else:
        atr_pct_value = atr_value / close_value * 100
    compression_z = _read_value(cols[compression_z_col], idx)

    compression_pass = False
    if compression_z is not None and atr_pct_value is not None:
        compression_pass = compression_z < compression_z_low

    tags["compression"] = "compression_pass" if compression_pass else "compression_fail"

    breakout_dir = "none"
    range_high = _read_value(cols[breakout_high_col], idx)
    range_low = _read_value(cols[breakout_low_col], idx)
    if close_value is not None and range_high is not None and range_low is not None:
        if close_value > range_high:
            breakout_dir = "up"
        elif close_value < range_low:
            breakout_dir = "down"
    tags["breakout_dir"] = breakout_dir

    bias_pass = False
    if ema200_value is not None and close_value is not None:
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
