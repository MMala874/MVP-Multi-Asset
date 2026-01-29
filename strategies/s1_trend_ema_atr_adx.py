from __future__ import annotations

from datetime import datetime
import importlib.util
from pathlib import Path
import sys
from typing import Any, Dict, Optional, Set

import pandas as pd

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types" / "__init__.py"
_spec = importlib.util.spec_from_file_location("project_types", _TYPES_PATH)
_types_module = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("project_types", _types_module)
assert _spec and _spec.loader
_spec.loader.exec_module(_types_module)

Side = _types_module.Side
SignalIntent = _types_module.SignalIntent

STRATEGY_ID = "s1_trend_ema_atr_adx"


def required_features() -> Set[str]:
    return {"ema_fast", "ema_slow", "adx", "atr"}


def _get_param(config: Dict[str, Any], key: str, default: Any) -> Any:
    return config.get(key, default)


def _read_value(series: pd.Series, idx: int) -> Optional[float]:
    value = series.iloc[idx]
    if pd.isna(value):
        return None
    return float(value)


def generate_signal(ctx: Dict[str, Any]) -> SignalIntent:
    df: pd.DataFrame = ctx["df"]
    idx: int = ctx["idx"]
    symbol: str = ctx["symbol"]
    current_time: datetime = ctx["current_time"]
    config: Dict[str, Any] = ctx.get("config", {})

    ema_fast_col = _get_param(config, "ema_fast_col", "ema_fast")
    ema_slow_col = _get_param(config, "ema_slow_col", "ema_slow")
    adx_col = _get_param(config, "adx_col", "adx")
    atr_col = _get_param(config, "atr_col", "atr")

    ema_fast = _read_value(df[ema_fast_col], idx)
    ema_slow = _read_value(df[ema_slow_col], idx)
    adx_value = _read_value(df[adx_col], idx)
    atr_value = _read_value(df[atr_col], idx)

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

    tp_points: Optional[float]
    if "k_tp" in config and atr_value is not None:
        tp_points = float(config["k_tp"]) * atr_value
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
