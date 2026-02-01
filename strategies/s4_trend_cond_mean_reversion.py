"""
S4: Trend-Conditioned Mean Reversion Strategy.

Uses H1 trend bias as direction filter + M15 Z-score mean reversion entries.
- Entry: M15 z-score deviation + H1 bias filter + M15 chop gate (ADX + slope)
- Exit: ATR-based SL/TP + orchestrator time stop
- Anti-lookahead: All features computed backward-only (shift(1) on H1)
"""

from __future__ import annotations

from typing import Any, Dict

from desk_types import Side, SignalIntent

import numpy as np


STRATEGY_ID = "S4_TREND_COND_MEAN_REVERSION"


def required_features() -> list[str]:
    """Features required by this strategy."""
    return [
        "close",
        "mr_z",
        "ema_base",
        "adx_m15",
        "ema_slope",
        "atr_pips",
        "trend_bias_h1",
    ]


def generate_signal(ctx: Dict[str, Any]) -> SignalIntent:
    """
    Generate signal for S4 trend-conditioned mean reversion.
    
    Args:
        ctx: Dict with keys:
            - cols: Dict[col_name, ndarray]
            - idx: current bar index
            - config: strategy parameters Dict
            - symbol: symbol name
            - current_time: timestamp
    
    Returns:
        SignalIntent with side, sl_points, tp_points, tags
    """
    cols = ctx.get("cols", {})
    idx = ctx.get("idx", -1)
    config = ctx.get("config", {})
    symbol = ctx.get("symbol", "")
    current_time = ctx.get("current_time", None)
    
    # Parameters
    z_entry = float(config.get("z_entry", 1.5))
    use_h1_bias = bool(config.get("use_h1_bias", True))
    adx_max_m15 = float(config.get("adx_max_m15", 18.0))
    slope_th = float(config.get("slope_th", 0.00003))
    k_sl = float(config.get("k_sl", 2.5))
    min_sl_points = float(config.get("min_sl_points", 8.0))
    k_tp = config.get("k_tp", None)
    if k_tp is not None:
        k_tp = float(k_tp)
    min_tp_points = float(config.get("min_tp_points", 5.0))
    
    # Read features - validate idx first
    if idx < 0 or isinstance(idx, (list, np.ndarray)):
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=symbol,
            side=Side.FLAT,
            signal_time=current_time,
            sl_points=None,
            tp_points=None,
            tags={"status": "idx_error"},
        )
    
    # Read mr_z
    try:
        mr_z_arr = cols.get("mr_z", np.array([]))
        if len(mr_z_arr) == 0 or idx >= len(mr_z_arr):
            return SignalIntent(
                strategy_id=STRATEGY_ID,
                symbol=symbol,
                side=Side.FLAT,
                signal_time=current_time,
                sl_points=None,
                tp_points=None,
                tags={"status": "mr_z_missing"},
            )
        mr_z = float(mr_z_arr[idx])
    except (KeyError, IndexError, TypeError, ValueError):
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=symbol,
            side=Side.FLAT,
            signal_time=current_time,
            sl_points=None,
            tp_points=None,
            tags={"status": "mr_z_error"},
        )
    
    # Check NaN
    if np.isnan(mr_z):
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=symbol,
            side=Side.FLAT,
            signal_time=current_time,
            sl_points=None,
            tp_points=None,
            tags={"status": "mr_z_nan"},
        )
    
    # Read adx_m15
    try:
        adx_m15_arr = cols.get("adx_m15", np.array([]))
        adx_m15 = float(adx_m15_arr[idx]) if len(adx_m15_arr) > idx else 0.0
    except (IndexError, TypeError, ValueError):
        adx_m15 = 0.0
    
    # Read ema_slope
    try:
        ema_slope_arr = cols.get("ema_slope", np.array([]))
        ema_slope = float(ema_slope_arr[idx]) if len(ema_slope_arr) > idx else 0.0
    except (IndexError, TypeError, ValueError):
        ema_slope = 0.0
    
    # Read atr_pips
    try:
        atr_pips_arr = cols.get("atr_pips", np.array([]))
        atr_pips = float(atr_pips_arr[idx]) if len(atr_pips_arr) > idx else 0.0
    except (IndexError, TypeError, ValueError):
        atr_pips = 0.0
    
    # Read H1 bias
    bias_h1 = 0
    bias_str = "flat"
    if use_h1_bias:
        try:
            bias_h1_arr = cols.get("trend_bias_h1", np.array([]))
            if len(bias_h1_arr) > idx:
                bias_h1 = int(bias_h1_arr[idx])
        except (IndexError, TypeError, ValueError):
            bias_h1 = 0
        
        if bias_h1 > 0:
            bias_str = "long"
        elif bias_h1 < 0:
            bias_str = "short"
        else:
            bias_str = "flat"
    
    # Gates
    adx_gate = "pass" if adx_m15 <= adx_max_m15 else "fail"
    slope_gate = "pass" if abs(ema_slope) <= slope_th else "fail"
    
    # Entry logic
    side = Side.FLAT
    
    # Z-score entry conditions
    long_z_signal = mr_z <= -z_entry
    short_z_signal = mr_z >= z_entry
    
    # H1 bias filtering
    if use_h1_bias:
        if bias_h1 == 0:
            # Flat bias -> no trades
            side = Side.FLAT
        elif bias_h1 > 0:
            # Long bias -> only LONG entries allowed
            if long_z_signal and adx_gate == "pass" and slope_gate == "pass":
                side = Side.LONG
        elif bias_h1 < 0:
            # Short bias -> only SHORT entries allowed
            if short_z_signal and adx_gate == "pass" and slope_gate == "pass":
                side = Side.SHORT
    else:
        # No H1 bias filter
        if long_z_signal and adx_gate == "pass" and slope_gate == "pass":
            side = Side.LONG
        elif short_z_signal and adx_gate == "pass" and slope_gate == "pass":
            side = Side.SHORT
    
    # If no valid side, return FLAT
    if side == Side.FLAT:
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=symbol,
            side=Side.FLAT,
            signal_time=current_time,
            sl_points=None,
            tp_points=None,
            tags={"status": "no_signal"},
        )
    
    # Compute SL/TP
    sl_points = max(k_sl * atr_pips, min_sl_points) if atr_pips > 0 else min_sl_points
    tp_points = None
    if k_tp is not None and atr_pips > 0:
        tp_points = max(k_tp * atr_pips, min_tp_points)
    
    # Build tags
    tags = {
        "bias_h1": bias_str,
        "z": f"{mr_z:.3f}",
        "adx_gate": adx_gate,
        "slope_gate": slope_gate,
    }
    
    return SignalIntent(
        strategy_id=STRATEGY_ID,
        symbol=symbol,
        side=side,
        signal_time=current_time,
        sl_points=sl_points,
        tp_points=tp_points,
        tags=tags,
    )
