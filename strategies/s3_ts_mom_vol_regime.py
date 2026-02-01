"""
S3_TS_MOM_VOL_REGIME: Time-Series Momentum Strategy with Volatility Regime Gating

Captures persistent directional moves using rolling returns (momentum).
Trades only when volatility regime supports trend continuation.
Anti-lookahead: signal on close(t), fill on open(t+1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np
import pandas as pd

from desk_types import SignalIntent, Side


STRATEGY_ID = "S3_TS_MOM_VOL_REGIME"


@dataclass
class MomSignalContext:
    """Input context for momentum signal generation."""
    cols: Dict[str, np.ndarray]  # {col_name: np.array}
    idx: int
    symbol: str
    current_time: pd.Timestamp
    config: object
    regime_snapshot: str


def generate_signal(ctx: MomSignalContext) -> SignalIntent:
    """
    Generate momentum-based signal with volatility regime gating.
    
    Returns SignalIntent with:
    - side: Side.LONG, Side.SHORT, or Side.FLAT
    - sl_points: stop loss in pips (SL)
    - tp_points: optional take profit in pips (default None for trailing)
    - tags: dict of signal metadata
    """
    
    # Extract parameters from config
    spec_params = _get_strategy_params(ctx.config, STRATEGY_ID)
    
    mom_window = int(spec_params.get("mom_window", 96))
    mom_th = float(spec_params.get("mom_th", 0.0))
    vol_ratio_th = float(spec_params.get("vol_ratio_th", 1.1))
    atr_min_pips = float(spec_params.get("atr_min_pips", 8.0))
    allowed_vol_regimes = spec_params.get("allowed_vol_regimes", ["MID", "HIGH"])
    spike_block = bool(spec_params.get("spike_block", False))
    k_sl = float(spec_params.get("k_sl", 2.5))
    min_sl_points = float(spec_params.get("min_sl_points", 8.0))
    
    tags_list = []
    
    # Ensure required columns exist
    required = ["mom", "vol_ratio", "atr_pips", "regime_snapshot"]
    for col in required:
        if col not in ctx.cols:
            tags_list.append(f"missing_{col}")
            return SignalIntent(
                strategy_id=STRATEGY_ID,
                symbol=ctx.symbol,
                side=Side.FLAT,
                signal_time=ctx.current_time,
                sl_points=None,
                tp_points=None,
                tags={"status": "missing_col", "missing": col}
            )
    
    # Extract arrays
    mom_arr = ctx.cols.get("mom", np.array([]))
    vol_ratio_arr = ctx.cols.get("vol_ratio", np.array([]))
    atr_pips_arr = ctx.cols.get("atr_pips", np.array([]))
    
    # Check if idx is valid
    if ctx.idx < 0 or ctx.idx >= len(mom_arr):
        tags_list.append("idx_out_of_bounds")
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=ctx.symbol,
            side=Side.FLAT,
            signal_time=ctx.current_time,
            sl_points=None,
            tp_points=None,
            tags={"status": "idx_error"}
        )
    
    # Check if momentum is valid (NaN before mom_window periods)
    if np.isnan(mom_arr[ctx.idx]):
        tags_list.append("mom_nan")
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=ctx.symbol,
            side=Side.FLAT,
            signal_time=ctx.current_time,
            sl_points=None,
            tp_points=None,
            tags={"status": "mom_nan"}
        )
    
    mom_val = float(mom_arr[ctx.idx])
    vol_ratio_val = float(vol_ratio_arr[ctx.idx])
    atr_pips_val = float(atr_pips_arr[ctx.idx])
    
    # ============ REGIME GATES ============
    tags_list.append(f"mom={mom_val:.6f}")
    tags_list.append(f"vol_ratio={vol_ratio_val:.2f}")
    
    # Parse regime snapshot
    regime_info = ctx.regime_snapshot or ""
    vol_regime = _extract_vol_regime(regime_info)
    spike_flag = _extract_spike_flag(regime_info)
    
    tags_list.append(f"vol_regime={vol_regime}")
    
    # Volatility regime gate
    if vol_regime not in allowed_vol_regimes:
        tags_list.append("vol_regime_reject")
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=ctx.symbol,
            side=Side.FLAT,
            signal_time=ctx.current_time,
            sl_points=None,
            tp_points=None,
            tags={"status": "vol_regime_reject"}
        )
    
    # Spike gate
    if spike_block and spike_flag == 1:
        tags_list.append("spike_reject")
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=ctx.symbol,
            side=Side.FLAT,
            signal_time=ctx.current_time,
            sl_points=None,
            tp_points=None,
            tags={"status": "spike_reject"}
        )
    
    # Vol ratio gate
    if vol_ratio_val < vol_ratio_th:
        tags_list.append("vol_ratio_reject")
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=ctx.symbol,
            side=Side.FLAT,
            signal_time=ctx.current_time,
            sl_points=None,
            tp_points=None,
            tags={"status": "vol_ratio_reject"}
        )
    
    # ATR pips gate
    if atr_pips_val < atr_min_pips:
        tags_list.append("atr_pips_reject")
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=ctx.symbol,
            side=Side.FLAT,
            signal_time=ctx.current_time,
            sl_points=None,
            tp_points=None,
            tags={"status": "atr_pips_reject"}
        )
    
    tags_list.append("gates_passed")
    
    # ============ MOMENTUM DIRECTION ============
    side = Side.FLAT
    
    if mom_val > mom_th:
        side = Side.LONG
        tags_list.append("long_signal")
    elif mom_val < -mom_th:
        side = Side.SHORT
        tags_list.append("short_signal")
    else:
        tags_list.append("momentum_neutral")
        return SignalIntent(
            strategy_id=STRATEGY_ID,
            symbol=ctx.symbol,
            side=Side.FLAT,
            signal_time=ctx.current_time,
            sl_points=None,
            tp_points=None,
            tags={"status": "momentum_neutral"}
        )
    
    # ============ RISK CALCULATION ============
    # SL in PIPS: sl_points = max(k_sl * atr_pips, min_sl_points)
    sl_points = max(k_sl * atr_pips_val, min_sl_points)
    
    # TP: default None for trailing stop, or compute if k_tp provided
    tp_points = None
    k_tp = spec_params.get("k_tp", None)
    if k_tp is not None:
        min_tp_points = float(spec_params.get("min_tp_points", 5.0))
        tp_points = max(float(k_tp) * atr_pips_val, min_tp_points)
        tags_list.append(f"tp={tp_points:.1f}")
    
    tags_list.append(f"sl={sl_points:.1f}")
    
    return SignalIntent(
        strategy_id=STRATEGY_ID,
        symbol=ctx.symbol,
        side=side,
        signal_time=ctx.current_time,
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
    ]


# ============ HELPER FUNCTIONS ============

def _get_strategy_params(config: object, strategy_id: str) -> dict:
    """Extract strategy params from config."""
    try:
        return config.strategies.params.get(strategy_id, {})
    except (AttributeError, KeyError):
        return {}


def _extract_vol_regime(regime_snapshot: str) -> str:
    """Extract VOL regime from snapshot string like 'VOL=LOW|SPIKE=0'."""
    if not regime_snapshot:
        return "UNKNOWN"
    
    parts = regime_snapshot.split("|")
    for part in parts:
        if part.startswith("VOL="):
            return part.replace("VOL=", "")
    
    return "UNKNOWN"


def _extract_spike_flag(regime_snapshot: str) -> int:
    """Extract SPIKE flag from snapshot string."""
    if not regime_snapshot:
        return 0
    
    parts = regime_snapshot.split("|")
    for part in parts:
        if part.startswith("SPIKE="):
            try:
                return int(part.replace("SPIKE=", ""))
            except ValueError:
                return 0
    
    return 0
