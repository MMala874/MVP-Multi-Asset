from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Set
from data.fx import PIP_SIZES

import numpy as np

from desk_types import Side, SignalIntent

STRATEGY_ID = "s1_trend_ema_atr_adx"


def required_features() -> Set[str]:
    return {"ema_fast", "ema_slow", "adx", "atr"}


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

    ema_fast_col = _get_param(config, "ema_fast_col", "ema_fast")
    ema_slow_col = _get_param(config, "ema_slow_col", "ema_slow")
    adx_col = _get_param(config, "adx_col", "adx")
    atr_col = _get_param(config, "atr_col", "atr_pips")

    ema_fast = _read_value(cols[ema_fast_col], idx)
    ema_slow = _read_value(cols[ema_slow_col], idx)
    adx_value = _read_value(cols[adx_col], idx)
    atr_value = _read_value(cols[atr_col], idx)

    if atr_value is None and atr_col == "atr_pips":
        # fallback: convert from price-ATR to pips if only "atr" exists
        atr_price = _read_value(cols.get("atr"), idx) if "atr" in cols else None
        pip_size = PIP_SIZES.get(symbol, 0.0001)
        atr_value = (atr_price / pip_size) if atr_price is not None else None


    tags: Dict[str, str] = {}
    side = Side.FLAT

    if ema_fast is None or ema_slow is None:
        tags["trend"] = "trend_unknown"
    elif ema_fast > ema_slow:
        tags["trend"] = "trend_up"
        side = Side.LONG
    elif ema_fast < ema_slow:
        tags["trend"] = "trend_down"
        side = Side.SHORT
    else:
        tags["trend"] = "trend_flat"

    adx_th = config.get("adx_th")
    adx_pass = True
    if adx_th is not None:
        if adx_value is None:
            adx_pass = False
        else:
            adx_pass = adx_value > float(adx_th)
    tags["adx_gate"] = "adx_pass" if adx_pass else "adx_fail"

    if not adx_pass:
        side = Side.FLAT

    k_sl = config.get("k_sl")
    sl_points: Optional[float]
    if k_sl is None or atr_value is None:
        sl_points = None
    else:
        sl_points = float(k_sl) * atr_value

    min_tp_points = float(_get_param(config, "min_tp_points", 5.0))
    tp_points: Optional[float]
    k_tp = config.get("k_tp")
    if k_tp is not None and atr_value is not None:
        tp_points = max(float(k_tp) * atr_value, min_tp_points)
    else:
        tp_points = None

    return SignalIntent(
        strategy_id=STRATEGY_ID,
        symbol=symbol,
        side=side,
        signal_time=current_time,
        sl_points=sl_points,
        tp_points=tp_points,
        tags=tags,
    )
