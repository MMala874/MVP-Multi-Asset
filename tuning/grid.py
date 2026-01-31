from __future__ import annotations

from itertools import product
from typing import Any, Dict, List, Literal


def build_grid_s1(preset: Literal["small", "medium", "large"] = "medium") -> List[Dict[str, Any]]:
    """Build grid search space for S1_TREND_EMA_ATR_ADX with preset sizes.
    
    Args:
        preset: Grid size preset
            - small: 1 × 1 × 3 × 2 × 1 × 1 × 1 = 6 combinations (minimal, fast)
            - medium: 3 × 2 × 4 × 4 × 3 × 2 × 2 = 1,152 combinations (balanced)
            - large: 5 × 3 × 5 × 5 × 4 × 3 × 3 = 13,500 combinations (comprehensive)
    """
    if preset == "small":
        ema_fast_vals = [20]
        ema_slow_vals = [50]
        adx_th_vals = [20, 25, 30]
        k_sl_vals = [2.0, 2.5]
        k_tp_vals = [1.5]
        min_sl_points_vals = [8.0]
        min_tp_points_vals = [8.0]
    elif preset == "medium":
        ema_fast_vals = [10, 20, 30]
        ema_slow_vals = [50, 100]
        adx_th_vals = [15, 20, 25, 30]
        k_sl_vals = [1.5, 2.0, 2.5, 3.0]
        k_tp_vals = [1.0, 1.5, 2.0]
        min_sl_points_vals = [5.0, 8.0]
        min_tp_points_vals = [5.0, 8.0]
    elif preset == "large":
        ema_fast_vals = [10, 15, 20, 25, 30]
        ema_slow_vals = [50, 75, 100]
        adx_th_vals = [15, 20, 25, 30, 35]
        k_sl_vals = [1.5, 2.0, 2.5, 3.0, 3.5]
        k_tp_vals = [1.0, 1.5, 2.0, 2.5]
        min_sl_points_vals = [5.0, 6.5, 8.0]
        min_tp_points_vals = [5.0, 6.5, 8.0]
    else:
        raise ValueError(f"Unknown preset: {preset}")

    grid = [
        {
            "ema_fast": ema_fast,
            "ema_slow": ema_slow,
            "adx_th": adx_th,
            "k_sl": k_sl,
            "k_tp": k_tp,
            "min_sl_points": min_sl_points,
            "min_tp_points": min_tp_points,
        }
        for ema_fast, ema_slow, adx_th, k_sl, k_tp, min_sl_points, min_tp_points in product(
            ema_fast_vals,
            ema_slow_vals,
            adx_th_vals,
            k_sl_vals,
            k_tp_vals,
            min_sl_points_vals,
            min_tp_points_vals,
        )
    ]
    return grid


def build_grid(strategy_id: str, preset: Literal["small", "medium", "large"] = "medium") -> List[Dict[str, Any]]:
    """Build grid for given strategy with preset size.
    
    Args:
        strategy_id: Strategy identifier
        preset: Grid size (small, medium, large)
    """
    if strategy_id == "S1_TREND_EMA_ATR_ADX":
        return build_grid_s1(preset)
    raise ValueError(f"Grid not defined for strategy: {strategy_id}")

