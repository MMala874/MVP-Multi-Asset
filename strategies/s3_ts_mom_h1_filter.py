"""
S3_TS_MOM_H1_FILTER: Time-Series Momentum with H1 Trend Filter

Architecture:
- H1 features (ema_fast_h1, ema_slow_h1, adx_h1) → trend_bias_h1
- M15 entry logic (momentum, regime)
- M15 execution (SL/TP based on ATR_short)

Anti-lookahead:
- H1 features merged via forward-fill (no shift)
- Entry signal on M15 close(t), fill on M15 open(t+1)
- One M15 bar never sees future H1 data
"""

from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pandas as pd

from desk_types import SignalIntent, Side


STRATEGY_ID = "S3_TS_MOM_H1_FILTER"


def generate_signal(ctx: Dict[str, Any]) -> SignalIntent:
    """
    Generate momentum-based signal with H1 trend filter, no lookahead.
    
    Entry gated by trend_bias_h1 (from H1 EMA/ADX).
    Execution on M15 momentum and volatility regime.
    """
    
    # Extract context fields
    cols = ctx.get("cols", {})
    idx = ctx.get("idx", -1)
    symbol = ctx.get("symbol", "")
    current_time = ctx.get("current_time", None)
    spec_params = ctx.get("config", {})
    
    # H1 parameters
    adx_th_h1 = float(spec_params.get("adx_th_h1", 25.0))
    
    # M15 parameters
    mom_window = int(spec_params.get("mom_window", 96))
    mom_th = float(spec_params.get("mom_th", 0.0))
    vol_ratio_th = float(spec_params.get("vol_ratio_th", 1.1))
    atr_min_pips = float(spec_params.get("atr_min_pips", 8.0))
    allowed_vol_regimes = spec_params.get("allowed_vol_regimes", ["MID", "HIGH"])
    spike_block = bool(spec_params.get("spike_block", False))
    k_sl = float(spec_params.get("k_sl", 2.5))
    min_sl_points = float(spec_params.get("min_sl_points", 8.0))
    
    tags_list = []
    
    # Check required M15 columns
    required_m15 = ["mom", "vol_ratio", "atr_pips", "regime_snapshot"]
    for col in required_m15:
        if col not in cols:
            tags_list.append(f"missing_{col}")
            return SignalIntent(
                strategy_id=STRATEGY_ID,
                symbol=symbol,
                side=Side.FLAT,
                signal_time=current_time,
                sl_points=None,
                tp_points=None,
                tags={"status": "missing_col", "missing": col}
            )
    
    # Check required H1 filter columns
    required_h1 = ["trend_bias_h1"]
    for col in required_h1:
        if col not in cols:
            tags_list.append(f"missing_h1_{col}")
            return SignalIntent(
                strategy_id=STRATEGY_ID,
                symbol=symbol,
                side=Side.FLAT,
                signal_time=current_time,
                sl_points=None,
                tp_points=None,
                tags={"status": "missing_h1_col", "missing": col}
            )
    
    # Extract arrays
    mom_arr = cols.get("mom", np.array([]))
    vol_ratio_arr = cols.get("vol_ratio", np.array([]))
    atr_pips_arr = cols.get("atr_pips", np.array([]))
    trend_bias_h1_arr = cols.get("trend_bias_h1", np.array([]))
    
    # Validate idx
    if idx < 0 or idx >= len(mom_arr):
        tags_list.append("idx_out_of_bounds")
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=symbol,
            side=Side.FLAT,
            signal_time=current_time,
            sl_points=None,
            tp_points=None,
            tags={"status": "idx_error"}
        )
    
    # Check if momentum is valid
    if np.isnan(mom_arr[idx]):
        tags_list.append("mom_nan")
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=symbol,
            side=Side.FLAT,
            signal_time=current_time,
            sl_points=None,
            tp_points=None,
            tags={"status": "mom_nan"}
        )
    
    mom_val = float(mom_arr[idx])
    vol_ratio_val = float(vol_ratio_arr[idx])
    atr_pips_val = float(atr_pips_arr[idx])
    trend_bias_h1_val = float(trend_bias_h1_arr[idx]) if not np.isnan(trend_bias_h1_arr[idx]) else 0.0
    
    # ============ H1 TREND FILTER ============
    tags_list.append(f"h1_bias={trend_bias_h1_val:.0f}")
    
    # H1 filter blocks FLAT bias
    if trend_bias_h1_val == 0:
        tags_list.append("h1_bias_flat_reject")
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=symbol,
            side=Side.FLAT,
            signal_time=current_time,
            sl_points=None,
            tp_points=None,
            tags={"status": "h1_bias_flat_reject"}
        )
    
    # ============ M15 REGIME GATES ============
    tags_list.append(f"mom={mom_val:.6f}")
    tags_list.append(f"vol_ratio={vol_ratio_val:.2f}")
    
    # Parse regime snapshot
    regime_info = cols.get("regime_snapshot", [""])[idx] if isinstance(cols.get("regime_snapshot"), np.ndarray) else ""
    vol_regime = _extract_vol_regime(regime_info)
    spike_flag = _extract_spike_flag(regime_info)
    
    tags_list.append(f"vol_regime={vol_regime}")
    
    # Volatility regime gate
    if vol_regime not in allowed_vol_regimes:
        tags_list.append("vol_regime_reject")
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=symbol,
            side=Side.FLAT,
            signal_time=current_time,
            sl_points=None,
            tp_points=None,
            tags={"status": "vol_regime_reject"}
        )
    
    # Spike gate
    if spike_block and spike_flag == 1:
        tags_list.append("spike_reject")
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=symbol,
            side=Side.FLAT,
            signal_time=current_time,
            sl_points=None,
            tp_points=None,
            tags={"status": "spike_reject"}
        )
    
    # Vol ratio gate
    if vol_ratio_val < vol_ratio_th:
        tags_list.append("vol_ratio_reject")
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=symbol,
            side=Side.FLAT,
            signal_time=current_time,
            sl_points=None,
            tp_points=None,
            tags={"status": "vol_ratio_reject"}
        )
    
    # ATR pips gate
    if atr_pips_val < atr_min_pips:
        tags_list.append("atr_pips_reject")
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=symbol,
            side=Side.FLAT,
            signal_time=current_time,
            sl_points=None,
            tp_points=None,
            tags={"status": "atr_pips_reject"}
        )
    
    tags_list.append("gates_passed")
    
    # ============ M15 MOMENTUM DIRECTION ============
    side = Side.FLAT
    
    if mom_val > mom_th:
        # M15 wants to go LONG
        # Entry gated by H1 trend_bias_h1 = +1 (LONG)
        if trend_bias_h1_val > 0:
            side = Side.LONG
            tags_list.append("long_signal_aligned")
        else:
            tags_list.append("long_mom_h1_short_bias_reject")
            return SignalIntent(
                strategy_id=STRATEGY_ID,
                symbol=symbol,
                side=Side.FLAT,
                signal_time=current_time,
                sl_points=None,
                tp_points=None,
                tags={"status": "long_mom_h1_short_bias_reject"}
            )
    elif mom_val < -mom_th:
        # M15 wants to go SHORT
        # Entry gated by H1 trend_bias_h1 = -1 (SHORT)
        if trend_bias_h1_val < 0:
            side = Side.SHORT
            tags_list.append("short_signal_aligned")
        else:
            tags_list.append("short_mom_h1_long_bias_reject")
            return SignalIntent(
                strategy_id=STRATEGY_ID,
                symbol=symbol,
                side=Side.FLAT,
                signal_time=current_time,
                sl_points=None,
                tp_points=None,
                tags={"status": "short_mom_h1_long_bias_reject"}
            )
    else:
        tags_list.append("momentum_neutral")
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=symbol,
            side=Side.FLAT,
            signal_time=current_time,
            sl_points=None,
            tp_points=None,
            tags={"status": "momentum_neutral"}
        )
    
    # ============ RISK CALCULATION ============
    # SL in PIPS based on M15 ATR
    sl_points = max(k_sl * atr_pips_val, min_sl_points)
    
    # TP: default None for trailing stop
    tp_points = None
    k_tp = spec_params.get("k_tp", None)
    if k_tp is not None:
        min_tp_points = float(spec_params.get("min_tp_points", 5.0))
        tp_points = max(float(k_tp) * atr_pips_val, min_tp_points)
        tags_list.append(f"tp={tp_points:.1f}")
    
    tags_list.append(f"sl={sl_points:.1f}")
    
    return SignalIntent(
        strategy_id=STRATEGY_ID,
        symbol=symbol,
        side=side,
        signal_time=current_time,
        sl_points=sl_points,
        tp_points=tp_points,
        tags={"status": "signal_generated", "details": ", ".join(tags_list)}
    )


def required_features() -> list[str]:
    """List of required data columns for this strategy."""
    return [
        "close",
        "r",
        "mom",
        "vol_ratio",
        "atr_short",
        "atr_long",
        "atr_pips",
        "regime_snapshot",
        "ema_fast_h1",
        "ema_slow_h1",
        "adx_h1",
        "trend_bias_h1",
    ]


# ============ HELPER FUNCTIONS ============

def _extract_vol_regime(regime_snapshot: str) -> str:
    """Extract VOL regime from snapshot string like 'VOL=LOW|SPIKE=0'."""
    if not regime_snapshot:
        return "UNKNOWN"
    
    parts = str(regime_snapshot).split("|")
    for part in parts:
        if part.startswith("VOL="):
            return part.replace("VOL=", "")
    
    return "UNKNOWN"


def _extract_spike_flag(regime_snapshot: str) -> int:
    """Extract SPIKE flag from snapshot string."""
    if not regime_snapshot:
        return 0
    
    parts = str(regime_snapshot).split("|")
    for part in parts:
        if part.startswith("SPIKE="):
            try:
                return int(part.replace("SPIKE=", ""))
            except ValueError:
                return 0
    
    return 0
