from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Set

import pandas as pd

from desk_types import Side, SignalIntent
from features.indicators import slope

STRATEGY_ID = "s2_mr_zscore_ema_regime"


def required_features() -> Set[str]:
    return {"close", "ema_base", "adx"}


def _get_param(config: Dict[str, Any], key: str, default: Any) -> Any:
    return config.get(key, default)


def _zscore(series: pd.Series, idx: int, window: int) -> Optional[float]:
    if idx + 1 < window:
        return None
    window_series = series.iloc[: idx + 1]
    rolling = window_series.rolling(window=window, min_periods=window)
    mean = rolling.mean().iloc[-1]
    std = rolling.std().iloc[-1]
    if pd.isna(mean) or pd.isna(std) or std == 0:
        return None
    return float((series.iloc[idx] - mean) / std)


def _rolling_slope(series: pd.Series, idx: int, window: int) -> Optional[float]:
    if idx + 1 < window:
        return None
    window_series = series.iloc[: idx + 1]
    slope_series = slope(window_series, window)
    value = slope_series.iloc[-1]
    if pd.isna(value):
        return None
    return float(value)


def generate_signal(ctx: Dict[str, Any]) -> SignalIntent:
    df: pd.DataFrame = ctx["df"]
    idx: int = ctx["idx"]
    symbol: str = ctx["symbol"]
    current_time: datetime = ctx["current_time"]
    config: Dict[str, Any] = ctx.get("config", {})

    close_col = _get_param(config, "close_col", "close")
    ema_base_col = _get_param(config, "ema_base_col", "ema_base")
    adx_col = _get_param(config, "adx_col", "adx")

    z_window = int(_get_param(config, "z_window", 30))
    slope_window = int(_get_param(config, "slope_window", 20))
    z_entry = float(_get_param(config, "z_entry", 2.0))
    adx_max = _get_param(config, "adx_max", 20.0)
    slope_th = float(_get_param(config, "slope_th", 0.01))

    closes = df[close_col]
    ema_base = df[ema_base_col]
    adx_value = df[adx_col].iloc[idx]

    z_value = _zscore(closes - ema_base, idx, z_window)
    slope_value = _rolling_slope(ema_base, idx, slope_window)

    gate_pass = True
    if pd.isna(adx_value):
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

    return SignalIntent(
        strategy_id=STRATEGY_ID,
        symbol=symbol,
        side=side,
        signal_time=current_time,
        sl_points=None,
        tp_points=None,
        tags=tags,
    )
