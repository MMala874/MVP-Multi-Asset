from __future__ import annotations

from datetime import datetime
import importlib.util
from pathlib import Path
import sys
from typing import Any, Dict, Optional, Set

import numpy as np
import pandas as pd

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types" / "__init__.py"
_spec = importlib.util.spec_from_file_location("project_types", _TYPES_PATH)
_types_module = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("project_types", _types_module)
assert _spec and _spec.loader
_spec.loader.exec_module(_types_module)

Side = _types_module.Side
SignalIntent = _types_module.SignalIntent

STRATEGY_ID = "s3_breakout_atr_regime_ema200"


def required_features() -> Set[str]:
    return {"high", "low", "close", "atr", "ema200"}


def _get_param(config: Dict[str, Any], key: str, default: Any) -> Any:
    return config.get(key, default)


def _rolling_percentile(series: pd.Series, window: int, percentile: float) -> Optional[float]:
    if len(series) < window:
        return None
    window_series = series.iloc[-window:].dropna()
    if len(window_series) < window:
        return None
    return float(np.percentile(window_series.to_numpy(), percentile))


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
    p_low = float(_get_param(config, "p_low", 20.0))
    breakout_window = int(_get_param(config, "breakout_window", 20))

    closes = df[close_col].iloc[: idx + 1]
    highs = df[high_col].iloc[: idx + 1]
    lows = df[low_col].iloc[: idx + 1]
    atr_values = df[atr_col].iloc[: idx + 1]
    ema200_value = df[ema200_col].iloc[idx]

    close_value = closes.iloc[-1]
    atr_value = atr_values.iloc[-1]

    tags: Dict[str, str] = {}

    atr_pct_series = atr_values / closes
    atr_pct_value = atr_value / close_value if close_value != 0 else np.nan
    compression_threshold = _rolling_percentile(
        atr_pct_series, compression_window, p_low
    )

    compression_pass = False
    if compression_threshold is not None and not pd.isna(atr_pct_value):
        compression_pass = atr_pct_value < compression_threshold

    tags["compression"] = "compression_pass" if compression_pass else "compression_fail"

    breakout_dir = "none"
    if idx >= breakout_window:
        range_high = highs.iloc[-breakout_window - 1 : -1].max()
        range_low = lows.iloc[-breakout_window - 1 : -1].min()
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
