from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Set

import numpy as np

from desk_types import Side, SignalIntent
STRATEGY_ID = "s2_mr_zscore_ema_regime"


def required_features() -> Set[str]:
    return {"close", "ema_base", "ema_slope", "adx", "mr_z", "atr"}


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

    ema_slope_col = _get_param(config, "ema_slope_col", "ema_slope")
    adx_col = _get_param(config, "adx_col", "adx")
    mr_z_col = _get_param(config, "mr_z_col", "mr_z")
    atr_col = _get_param(config, "atr_col", "atr")

    z_entry = float(_get_param(config, "z_entry", 2.0))
    adx_max = _get_param(config, "adx_max", 20.0)
    slope_th = float(_get_param(config, "slope_th", 0.01))
    k_sl = float(_get_param(config, "k_sl", 2.0))
    min_sl_points = float(_get_param(config, "min_sl_points", 5.0))

    adx_value = _read_value(cols[adx_col], idx)
    z_value = _read_value(cols[mr_z_col], idx)
    slope_value = _read_value(cols[ema_slope_col], idx)
    atr_value = _read_value(cols[atr_col], idx)

    gate_pass = True
    if adx_value is None:
        gate_pass = False
    elif adx_max is not None and float(adx_value) >= float(adx_max):
        gate_pass = False

    if slope_value is None or abs(slope_value) >= slope_th:
        gate_pass = False

    tags: Dict[str, str] = {}

    if z_value is None:
        tags["z_bucket"] = "z_unknown"
    elif z_value >= z_entry:
        tags["z_bucket"] = "z_high_pos"
    elif z_value <= -z_entry:
        tags["z_bucket"] = "z_high_neg"
    else:
        tags["z_bucket"] = "z_neutral"

    tags["gate"] = "gate_pass" if gate_pass else "gate_fail"

    side = Side.FLAT
    if gate_pass and z_value is not None:
        if z_value >= z_entry:
            side = Side.SHORT
        elif z_value <= -z_entry:
            side = Side.LONG

    if side != Side.FLAT and atr_value is None:
        tags["missing_atr"] = "true"
        side = Side.FLAT

    sl_points = None
    if side != Side.FLAT:
        sl_points = max(k_sl * atr_value, min_sl_points)

    return SignalIntent(
        strategy_id=STRATEGY_ID,
        symbol=symbol,
        side=side,
        signal_time=current_time,
        sl_points=sl_points,
        tp_points=None,
        tags=tags,
    )
