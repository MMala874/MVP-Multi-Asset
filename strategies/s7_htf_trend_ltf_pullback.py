"""
S7_HTF_TREND_LTF_PULLBACK: HTF Trend (H4) with LTF Pullback (M15)

Architecture:
- H4 → Trend bias (DIRECTION): EMA fast > slow + ADX > threshold = +1 (LONG), -1 (SHORT), 0 (FLAT)
- H1 → Trailing & stop management: ATR, Chandelier Exit
- M15 → Entry timing: Pullback + continuation pattern

Anti-lookahead:
- H4 features merged via shift(1) before merge_asof to M15 (closed bars only)
- H1 features for stop/trailing (also shift(1))
- M15 entry signal on close(t), fill on open(t+1)

Key Rules:
- Entry ONLY when trend_bias_h4 aligns (no counter-trend trades)
- Pullback between 0.3 and 1.2 ATR (avoids spikes)
- Trailing stop from H1 Chandelier (no fixed TP)
- Low frequency, high quality trades targeting 30-100 pips
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Set

import numpy as np
import pandas as pd

from desk_types import SignalIntent, Side
from data.fx import PIP_SIZES

STRATEGY_ID = "S7_HTF_TREND_LTF_PULLBACK"


def required_features() -> Set[str]:
    """Features required for this strategy (from H4, H1, M15 merged into M15 df)."""
    return {
        # H4 features (merged, shift(1))
        "ema_fast_h4",
        "ema_slow_h4",
        "adx_h4",
        "trend_bias_h4",
        # H1 features (merged, shift(1), in PIPS units)
        "atr_h1_pips",
        "chandelier_exit_h1",
        # M15 features
        "ema_pullback",
        "ema_trend",
        "atr_m15",
        "pullback_depth",
        "ema_slope_m15",
    }


def _read_value(values: np.ndarray, idx: int) -> Optional[float]:
    """Safely read a value from array, handling NaN/None."""
    if idx < 0 or idx >= len(values):
        return None
    value = values[idx]
    if value is None:
        return None
    if isinstance(value, (float, np.floating)) and np.isnan(value):
        return None
    return float(value)


def generate_signal(ctx: Dict[str, Any]) -> SignalIntent:
    """
    Generate pullback entry signal gated by HTF trend bias.
    
    Entry:
    - H4 trend_bias_h4 gates direction (no counter-trend)
    - M15 pullback valid: 0.3 <= pullback_depth <= 1.2
    - M15 entry: close crosses above/below EMA20
    - EMA slope confirms direction
    
    Stop/Trailing:
    - SL = max(2.0 * ATR_H1, min_sl_pips)
    - Trailing from H1 Chandelier
    
    No fixed TP: Let trends run.
    """
    cols: Dict[str, np.ndarray] = ctx.get("cols", {})
    idx: int = ctx.get("idx", -1)
    symbol: str = ctx.get("symbol", "")
    current_time: Any = ctx.get("current_time")
    config: Dict[str, Any] = ctx.get("config", {})
    
    tags: Dict[str, str] = {}
    side = Side.FLAT
    sl_points: Optional[float] = None
    tp_points: Optional[float] = None
    
    # ========== PARAMETER EXTRACTION ==========
    adx_min_h4 = float(config.get("adx_min_h4", 20.0))
    pullback_min = float(config.get("pullback_min", 0.3))
    pullback_max = float(config.get("pullback_max", 1.2))
    k_sl_h1 = float(config.get("k_sl_h1", 2.0))
    min_sl_points = float(config.get("min_sl_points", 15.0))
    
    # ========== VALIDATE INDEX & COLUMNS ==========
    if idx < 0:
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=symbol,
            side=Side.FLAT,
            signal_time=current_time,
            sl_points=None,
            tp_points=None,
            tags={"status": "idx_invalid"}
        )
    
    required_cols = list(required_features())
    missing_cols = [c for c in required_cols if c not in cols]
    if missing_cols:
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=symbol,
            side=Side.FLAT,
            signal_time=current_time,
            sl_points=None,
            tp_points=None,
            tags={"status": "missing_features", "missing": ",".join(missing_cols)}
        )
    
    # ========== READ VALUES FROM ARRAYS ==========
    trend_bias_h4 = _read_value(cols["trend_bias_h4"], idx)
    adx_h4 = _read_value(cols["adx_h4"], idx)
    pullback_depth = _read_value(cols["pullback_depth"], idx)
    ema_slope_m15 = _read_value(cols["ema_slope_m15"], idx)
    ema_pullback = _read_value(cols["ema_pullback"], idx)
    atr_m15 = _read_value(cols["atr_m15"], idx)
    atr_h1_pips = _read_value(cols["atr_h1_pips"], idx)  # Already in pips from prepare_h1_features_with_atr
    close = _read_value(cols["close"], idx)
    
    # ========== VALIDATE CRITICAL VALUES ==========
    if trend_bias_h4 is None or adx_h4 is None:
        tags["bias_h4"] = "unknown"
        tags["adx_h4"] = "unknown"
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=symbol,
            side=Side.FLAT,
            signal_time=current_time,
            sl_points=None,
            tp_points=None,
            tags=tags
        )
    
    if pullback_depth is None or ema_slope_m15 is None or ema_pullback is None or atr_m15 is None or atr_h1_pips is None or close is None:
        tags["bias_h4"] = str(int(trend_bias_h4))
        tags["adx_h4"] = f"{adx_h4:.1f}"
        tags["status"] = "missing_m15_value"
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=symbol,
            side=Side.FLAT,
            signal_time=current_time,
            sl_points=None,
            tp_points=None,
            tags=tags
        )
    
    # ========== TAG DEBUG INFO ==========
    tags["bias_h4"] = str(int(trend_bias_h4))
    tags["adx_h4"] = f"{adx_h4:.1f}"
    tags["pullback_depth"] = f"{pullback_depth:.2f}"
    tags["ema_slope_m15"] = f"{ema_slope_m15:.6f}"
    tags["atr_h1_pips"] = f"{atr_h1_pips:.1f}"
    
    # ========== H4 TREND BIAS GATE ==========
    # Only trade in direction of H4 bias; reject flat or opposite direction
    if trend_bias_h4 == 0:
        tags["entry_reason"] = "h4_bias_flat"
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=symbol,
            side=Side.FLAT,
            signal_time=current_time,
            sl_points=None,
            tp_points=None,
            tags=tags
        )
    
    # ========== H4 ADX STRENGTH GATE ==========
    # Only trade if H4 trend is strong enough
    if adx_h4 < adx_min_h4:
        tags["entry_reason"] = f"adx_h4_weak_{adx_h4:.1f}<{adx_min_h4:.1f}"
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=symbol,
            side=Side.FLAT,
            signal_time=current_time,
            sl_points=None,
            tp_points=None,
            tags=tags
        )
    
    # ========== M15 PULLBACK VALIDATION ==========
    # Pullback must be within valid range (avoids spikes, enters during pullback)
    if not (pullback_min <= pullback_depth <= pullback_max):
        tags["entry_reason"] = f"pullback_out_of_range_{pullback_depth:.2f}"
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=symbol,
            side=Side.FLAT,
            signal_time=current_time,
            sl_points=None,
            tp_points=None,
            tags=tags
        )
    
    # ========== M15 EMA SLOPE CHECK ==========
    # EMA slope must be consistent with bias (trending, not reverting)
    slope_th = 0.00001  # Tiny threshold to check direction
    if trend_bias_h4 > 0 and ema_slope_m15 <= -slope_th:
        # LONG bias but EMA slope negative → trend weakening
        tags["entry_reason"] = "ema_slope_bearish_vs_long_bias"
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=symbol,
            side=Side.FLAT,
            signal_time=current_time,
            sl_points=None,
            tp_points=None,
            tags=tags
        )
    
    if trend_bias_h4 < 0 and ema_slope_m15 >= slope_th:
        # SHORT bias but EMA slope positive → trend weakening
        tags["entry_reason"] = "ema_slope_bullish_vs_short_bias"
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=symbol,
            side=Side.FLAT,
            signal_time=current_time,
            sl_points=None,
            tp_points=None,
            tags=tags
        )
    
    # ========== PULLBACK CONTINUATION ENTRY ==========
    # Entry on M15 close crossing EMA20 in direction of H4 bias
    
    if trend_bias_h4 > 0:
        # LONG: close above EMA pullback after pullback
        if close > ema_pullback:
            side = Side.LONG
            tags["entry_reason"] = "pullback_continuation_long"
        else:
            tags["entry_reason"] = "pullback_no_cross_long"
            return SignalIntent(
                strategy_id=STRATEGY_ID,
                symbol=symbol,
                side=Side.FLAT,
                signal_time=current_time,
                sl_points=None,
                tp_points=None,
                tags=tags
            )
    else:  # trend_bias_h4 < 0
        # SHORT: close below EMA pullback after pullback
        if close < ema_pullback:
            side = Side.SHORT
            tags["entry_reason"] = "pullback_continuation_short"
        else:
            tags["entry_reason"] = "pullback_no_cross_short"
            return SignalIntent(
                strategy_id=STRATEGY_ID,
                symbol=symbol,
                side=Side.FLAT,
                signal_time=current_time,
                sl_points=None,
                tp_points=None,
                tags=tags
            )
    
    # ========== STOP LOSS CALCULATION ==========
    # SL = max(k_sl_h1 * ATR_H1_PIPS, min_sl_pips)
    # atr_h1_pips is already in pip units from prepare_h1_features_with_atr
    sl_points = max(k_sl_h1 * atr_h1_pips, min_sl_points)
    
    # No fixed TP: Let H1 Chandelier handle trailing
    tp_points = None
    
    tags["sl_points"] = f"{sl_points:.1f}"
    
    return SignalIntent(
        strategy_id=STRATEGY_ID,
        symbol=symbol,
        side=side,
        signal_time=current_time,
        sl_points=sl_points,
        tp_points=tp_points,
        tags=tags
    )
