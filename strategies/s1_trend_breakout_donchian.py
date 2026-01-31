"""
S1 Trend Regime + Donchian Breakout Entry Strategy

Combines:
- EMA/ADX for trend bias and volatility regime
- Donchian breakout (recent high/low, not last bar) for entry timing
- Volatility regime & spike filters to reduce overtrading
- Breakout confirmation (1-bar) to avoid fake breaks
- Cooldown to prevent machine-gun entries

No lookahead: Uses shift(1) for Donchian computation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Set
from data.fx import PIP_SIZES

import numpy as np

from desk_types import Side, SignalIntent

STRATEGY_ID = "s1_trend_breakout_donchian"


def required_features() -> Set[str]:
    """Features that must be precomputed in orchestrator."""
    return {
        "close", "high", "low",
        "ema_fast", "ema_slow",
        "adx",
        "atr",           # price units
        "atr_pips",      # pips
        "breakout_hh",   # Donchian high (with shift(1))
        "breakout_ll",   # Donchian low (with shift(1))
        "regime_snapshot",  # VOL=... and SPIKE=...
    }


def _get_param(config: Dict[str, Any], key: str, default: Any) -> Any:
    """Safe parameter retrieval."""
    return config.get(key, default)


def _read_value(values: np.ndarray, idx: int) -> Optional[float]:
    """Safely read a value from an array, handling NaN and None."""
    if idx < 0 or idx >= len(values):
        return None
    value = values[idx]
    if value is None:
        return None
    if isinstance(value, (float, np.floating)) and np.isnan(value):
        return None
    return float(value)


def _parse_regime_snapshot(regime_str: str) -> tuple[str, int]:
    """
    Parse regime_snapshot format: "VOL=<LOW|MID|HIGH>|SPIKE=<0|1>"
    Returns: (vol_regime, spike_flag)
    """
    try:
        parts = regime_str.split("|")
        vol_part = [p for p in parts if p.startswith("VOL=")]
        spike_part = [p for p in parts if p.startswith("SPIKE=")]
        
        vol = vol_part[0].replace("VOL=", "") if vol_part else "UNKNOWN"
        spike = int(spike_part[0].replace("SPIKE=", "")) if spike_part else 0
        
        return vol, spike
    except (AttributeError, IndexError, ValueError):
        return "UNKNOWN", 0


def generate_signal(ctx: Dict[str, Any]) -> SignalIntent:
    """
    Generate trading signal based on Donchian breakout + EMA/ADX regime.
    
    Entry conditions:
    1. Bias from EMA (fast > slow = LONG bias, fast < slow = SHORT bias)
    2. ADX gate (adx > adx_th, optionally rising)
    3. Volatility regime gate (allow MID/HIGH by default, block SPIKE if enabled)
    4. Donchian breakout with buffer
    5. 1-bar confirmation (price was near/inside breakout on previous bar)
    6. Cooldown check (last_exit_idx tracking)
    """
    cols: Dict[str, np.ndarray] = ctx["cols"]
    idx: int = ctx["idx"]
    symbol: str = ctx["symbol"]
    current_time: datetime = ctx["current_time"]
    config: Dict[str, Any] = ctx.get("config", {})
    
    tags: Dict[str, str] = {}
    side = Side.FLAT
    
    # ========================
    # 1. Read values from cols
    # ========================
    ema_fast = _read_value(cols["ema_fast"], idx)
    ema_slow = _read_value(cols["ema_slow"], idx)
    adx_value = _read_value(cols.get("adx"), idx)
    atr_price = _read_value(cols.get("atr"), idx)
    atr_pips_value = _read_value(cols.get("atr_pips"), idx)
    
    close = _read_value(cols["close"], idx)
    high = _read_value(cols["high"], idx)
    low = _read_value(cols["low"], idx)
    
    breakout_hh = _read_value(cols.get("breakout_hh"), idx)
    breakout_ll = _read_value(cols.get("breakout_ll"), idx)
    
    regime_snapshot = cols.get("regime_snapshot")
    if regime_snapshot is not None:
        regime_str = regime_snapshot[idx] if idx < len(regime_snapshot) else None
    else:
        regime_str = None
    
    # ========================
    # 2. Trend bias from EMA
    # ========================
    if ema_fast is None or ema_slow is None:
        tags["ema_bias"] = "unknown"
        side = Side.FLAT
    elif ema_fast > ema_slow:
        tags["ema_bias"] = "long"
        side = Side.LONG
    elif ema_fast < ema_slow:
        tags["ema_bias"] = "short"
        side = Side.SHORT
    else:
        tags["ema_bias"] = "neutral"
        side = Side.FLAT
    
    # ========================
    # 3. ADX gate
    # ========================
    adx_th = config.get("adx_th")
    adx_rising = bool(config.get("adx_rising", False))
    adx_pass = True
    
    if adx_th is not None:
        if adx_value is None:
            adx_pass = False
            tags["adx_gate"] = "no_value"
        elif adx_value <= float(adx_th):
            adx_pass = False
            tags["adx_gate"] = f"low ({adx_value:.1f}<{adx_th})"
        else:
            # ADX passes threshold check
            if adx_rising and idx > 0:
                adx_prev = _read_value(cols.get("adx"), idx - 1)
                if adx_prev is not None and adx_value <= adx_prev:
                    adx_pass = False
                    tags["adx_gate"] = f"not_rising ({adx_value:.1f}<={adx_prev:.1f})"
                else:
                    tags["adx_gate"] = "pass"
            else:
                tags["adx_gate"] = "pass"
    
    if not adx_pass:
        side = Side.FLAT
    
    # ========================
    # 4. Volatility regime gate
    # ========================
    allowed_vol_regimes = config.get("allowed_vol_regimes", ["MID", "HIGH"])
    spike_block = bool(config.get("spike_block", False))
    regime_pass = True
    
    if regime_str is not None:
        vol, spike = _parse_regime_snapshot(regime_str)
        tags["regime"] = f"{vol}|spike={spike}"
        
        if vol not in allowed_vol_regimes:
            regime_pass = False
            tags["regime_gate"] = f"vol_blocked ({vol})"
        elif spike_block and spike == 1:
            regime_pass = False
            tags["regime_gate"] = "spike_blocked"
        else:
            tags["regime_gate"] = "pass"
    else:
        tags["regime"] = "unknown"
        tags["regime_gate"] = "no_snapshot"
        regime_pass = False
    
    if not regime_pass:
        side = Side.FLAT
    
    # ========================
    # 5. Donchian breakout
    # ========================
    buffer_atr = float(config.get("buffer_atr", 0.1))
    breakout_pass = True
    
    if close is None or breakout_hh is None or breakout_ll is None or atr_price is None:
        breakout_pass = False
        tags["breakout"] = "missing_data"
    else:
        buffer_price = buffer_atr * atr_price
        
        if side == Side.LONG:
            # LONG: close > breakout_hh + buffer
            if close > breakout_hh + buffer_price:
                tags["breakout"] = "long_break"
            else:
                breakout_pass = False
                tags["breakout"] = f"no_long_break (c={close:.5f} vs hh+buf={breakout_hh + buffer_price:.5f})"
        elif side == Side.SHORT:
            # SHORT: close < breakout_ll - buffer
            if close < breakout_ll - buffer_price:
                tags["breakout"] = "short_break"
            else:
                breakout_pass = False
                tags["breakout"] = f"no_short_break (c={close:.5f} vs ll-buf={breakout_ll - buffer_price:.5f})"
        else:
            breakout_pass = False
            tags["breakout"] = "no_side"
    
    if not breakout_pass:
        side = Side.FLAT
    
    # ========================
    # 6. Breakout confirmation (1-bar)
    # ========================
    confirmation_pass = True
    if side != Side.FLAT and idx > 0:
        # Previous bar values
        close_prev = _read_value(cols["close"], idx - 1)
        breakout_hh_prev = _read_value(cols.get("breakout_hh"), idx - 1)
        breakout_ll_prev = _read_value(cols.get("breakout_ll"), idx - 1)
        atr_price_prev = _read_value(cols.get("atr"), idx - 1)
        
        if close_prev is None or breakout_hh_prev is None or breakout_ll_prev is None or atr_price_prev is None:
            confirmation_pass = False
            tags["confirmation"] = "missing_prev_data"
        else:
            buffer_price_prev = buffer_atr * atr_price_prev
            
            if side == Side.LONG:
                # Previous bar should be <= breakout_hh_prev + buffer_prev
                if close_prev <= breakout_hh_prev + buffer_price_prev:
                    tags["confirmation"] = "confirmed"
                else:
                    confirmation_pass = False
                    tags["confirmation"] = f"not_confirmed_long (prev={close_prev:.5f} vs hh+buf={breakout_hh_prev + buffer_price_prev:.5f})"
            elif side == Side.SHORT:
                # Previous bar should be >= breakout_ll_prev - buffer_prev
                if close_prev >= breakout_ll_prev - buffer_price_prev:
                    tags["confirmation"] = "confirmed"
                else:
                    confirmation_pass = False
                    tags["confirmation"] = f"not_confirmed_short (prev={close_prev:.5f} vs ll-buf={breakout_ll_prev - buffer_price_prev:.5f})"
    else:
        if side != Side.FLAT and idx == 0:
            tags["confirmation"] = "skipped_at_idx0"
        else:
            tags["confirmation"] = "no_entry"
    
    if not confirmation_pass:
        side = Side.FLAT
    
    # ========================
    # 7. Cooldown (anti-machine-gun)
    # ========================
    cooldown_bars = int(config.get("cooldown_bars", 0))
    if cooldown_bars > 0:
        # Get last_exit_idx from context if tracking cooldown per strategy+symbol
        last_exit_idx = ctx.get("last_exit_idx", -cooldown_bars - 1)
        if idx - last_exit_idx < cooldown_bars:
            tags["cooldown"] = f"active ({idx - last_exit_idx} < {cooldown_bars})"
            side = Side.FLAT
        else:
            tags["cooldown"] = "none"
    
    # ========================
    # 8. Stop Loss & Take Profit (in pips)
    # ========================
    sl_points: Optional[float] = None
    tp_points: Optional[float] = None
    
    if side != Side.FLAT and atr_pips_value is not None:
        k_sl = config.get("k_sl")
        min_sl_points = float(config.get("min_sl_points", 5.0))
        
        if k_sl is not None:
            sl_points = max(float(k_sl) * atr_pips_value, min_sl_points)
        
        k_tp = config.get("k_tp")
        min_tp_points = float(config.get("min_tp_points", 10.0))
        if k_tp is not None:
            tp_points = max(float(k_tp) * atr_pips_value, min_tp_points)
    
    return SignalIntent(
        strategy_id=STRATEGY_ID,
        symbol=symbol,
        side=side,
        signal_time=current_time,
        sl_points=sl_points,
        tp_points=tp_points,
        tags=tags,
    )
