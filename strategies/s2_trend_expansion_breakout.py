"""
S2 Trend Expansion Breakout Strategy

Philosophy:
- Trade RARELY via volatility expansion filter
- Enter only when volatility EXPANDS after compression
- Capture LARGE moves using ATR-based position sizing
- Beat costs via move size, not win rate

Core logic:
1. Identify trend bias (EMA fast > slow = LONG)
2. Wait for volatility compression (vol_ratio low)
3. Then trade breakout when volatility EXPANDS
4. True Range impulse must be strong (large moves)
5. Use trailing stop via chandelier concept

No lookahead: All features use shift(1) or historical data only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Set

import numpy as np

from desk_types import Side, SignalIntent

STRATEGY_ID = "S2_TREND_EXPANSION_BREAKOUT"


def required_features() -> Set[str]:
    """Features that must be precomputed in orchestrator."""
    return {
        "close", "high", "low", "open",
        "ema_fast", "ema_slow",
        "atr_short", "atr_long",
        "atr_pips",
        "breakout_hh", "breakout_ll",
        "vol_ratio",
        "regime_snapshot",  # For VOL/SPIKE info
    }


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
    """Parse regime_snapshot format: "VOL=<LOW|MID|HIGH>|SPIKE=<0|1>"."""
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
    Generate trading signal based on volatility expansion + breakout.
    
    Entry conditions (ALL must be met):
    1. Volatility has expanded (vol_ratio > threshold)
    2. ATR is large enough (atr_short > atr_min)
    3. Trend bias agrees with direction
    4. Price breaks Donchian level
    5. True Range impulse is strong
    """
    cols: Dict[str, np.ndarray] = ctx["cols"]
    idx: int = ctx["idx"]
    symbol: str = ctx["symbol"]
    current_time: datetime = ctx["current_time"]
    config: Dict[str, Any] = ctx.get("config", {})
    
    tags: Dict[str, str] = {}
    side = Side.FLAT
    
    # ========================
    # Read values
    # ========================
    ema_fast = _read_value(cols.get("ema_fast"), idx)
    ema_slow = _read_value(cols.get("ema_slow"), idx)
    atr_short = _read_value(cols.get("atr_short"), idx)
    atr_long = _read_value(cols.get("atr_long"), idx)
    atr_pips_value = _read_value(cols.get("atr_pips"), idx)
    
    close = _read_value(cols["close"], idx)
    high = _read_value(cols["high"], idx)
    low = _read_value(cols["low"], idx)
    open_price = _read_value(cols.get("open"), idx)
    
    breakout_hh = _read_value(cols.get("breakout_hh"), idx)
    breakout_ll = _read_value(cols.get("breakout_ll"), idx)
    vol_ratio = _read_value(cols.get("vol_ratio"), idx)
    
    regime_snapshot = cols.get("regime_snapshot")
    if regime_snapshot is not None:
        regime_str = regime_snapshot[idx] if idx < len(regime_snapshot) else None
    else:
        regime_str = None
    
    # ========================
    # 1. Trend bias from EMA
    # ========================
    if ema_fast is None or ema_slow is None:
        tags["trend"] = "unknown"
        side = Side.FLAT
    elif ema_fast > ema_slow:
        tags["trend"] = "bias_long"
        side = Side.LONG
    elif ema_fast < ema_slow:
        tags["trend"] = "bias_short"
        side = Side.SHORT
    else:
        tags["trend"] = "neutral"
        side = Side.FLAT
    
    # ========================
    # 2. Volatility expansion gate
    # ========================
    vol_ratio_th = float(config.get("vol_ratio_th", 1.1))
    atr_min_pips = float(config.get("atr_min_pips", 8))
    vol_pass = True
    
    if vol_ratio is None or atr_short is None or atr_pips_value is None:
        vol_pass = False
        tags["vol_gate"] = "fail_no_data"
    elif vol_ratio <= vol_ratio_th:
        vol_pass = False
        tags["vol_gate"] = "fail_compression"
    elif atr_pips_value < atr_min_pips:
        vol_pass = False
        tags["vol_gate"] = "fail_atr_min"
    else:
        tags["vol_gate"] = "pass"
    
    if not vol_pass:
        side = Side.FLAT
    
    # ========================
    # 3. Regime check (optional spike block)
    # ========================
    allowed_vol_regimes = config.get("allowed_vol_regimes", ["MID", "HIGH"])
    spike_block = bool(config.get("spike_block", False))
    regime_pass = True
    
    if regime_str is not None:
        vol, spike = _parse_regime_snapshot(regime_str)
        tags["regime"] = f"{vol}|spike={spike}"
        
        if vol not in allowed_vol_regimes:
            regime_pass = False
            tags["regime_gate"] = "fail"
        elif spike_block and spike == 1:
            regime_pass = False
            tags["regime_gate"] = "fail_spike"
        else:
            tags["regime_gate"] = "pass"
    else:
        tags["regime"] = "unknown"
        tags["regime_gate"] = "pass"
    
    if not regime_pass:
        side = Side.FLAT
    
    # ========================
    # 4. Breakout condition
    # ========================
    buffer_atr = float(config.get("buffer_atr", 0.2))
    breakout_pass = True
    
    if close is None or breakout_hh is None or breakout_ll is None or atr_short is None:
        breakout_pass = False
        tags["breakout"] = "fail_no_data"
    else:
        buffer_price = buffer_atr * atr_short
        
        if side == Side.LONG:
            if close > breakout_hh + buffer_price:
                tags["breakout"] = "pass_long"
            else:
                breakout_pass = False
                tags["breakout"] = "fail_long"
        elif side == Side.SHORT:
            if close < breakout_ll - buffer_price:
                tags["breakout"] = "pass_short"
            else:
                breakout_pass = False
                tags["breakout"] = "fail_short"
        else:
            breakout_pass = False
            tags["breakout"] = "fail_no_side"
    
    if not breakout_pass:
        side = Side.FLAT
    
    # ========================
    # 5. True Range impulse gate
    # ========================
    impulse_th = float(config.get("impulse_th", 1.2))
    impulse_pass = True
    
    if idx > 0 and high is not None and low is not None:
        # True range for current bar
        prev_close = _read_value(cols["close"], idx - 1)
        tr = max(
            high - low,
            abs(high - prev_close) if prev_close else 0,
            abs(low - prev_close) if prev_close else 0,
        )
        
        if atr_short is not None and atr_short > 0:
            impulse = tr / atr_short
            tags["impulse"] = f"{impulse:.2f}"
            
            if impulse <= impulse_th:
                impulse_pass = False
                tags["impulse_gate"] = "fail"
            else:
                tags["impulse_gate"] = "pass"
        else:
            tags["impulse_gate"] = "fail_no_atr"
            impulse_pass = False
    else:
        tags["impulse_gate"] = "skip"
        impulse_pass = False
    
    if not impulse_pass:
        side = Side.FLAT
    
    # ========================
    # 6. Stop Loss (ATR-based)
    # ========================
    sl_points: Optional[float] = None
    tp_points: Optional[float] = None
    
    if side != Side.FLAT and atr_pips_value is not None and atr_pips_value > 0:
        k_sl = config.get("k_sl", 3.0)
        min_sl_points = float(config.get("min_sl_points", 8))
        
        if k_sl is not None:
            sl_points = max(float(k_sl) * atr_pips_value, min_sl_points)
        
        # No fixed TP - trailing stop is managed by orchestrator
    
    return SignalIntent(
        strategy_id=STRATEGY_ID,
        symbol=symbol,
        side=side,
        signal_time=current_time,
        sl_points=sl_points,
        tp_points=tp_points,
        tags=tags,
    )
