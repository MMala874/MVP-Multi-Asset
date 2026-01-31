from __future__ import annotations

from itertools import product
from typing import Any, Dict, List


def build_grid_s1() -> List[Dict[str, Any]]:
    """Build grid search space for S1_TREND_EMA_ATR_ADX."""
    ema_fast_vals = [10, 20, 30]
    ema_slow_vals = [50, 100]
    adx_th_vals = [15, 20, 25, 30]
    k_sl_vals = [1.5, 2.0, 2.5, 3.0]
    k_tp_vals = [1.0, 1.5, 2.0]
    min_sl_points_vals = [5.0, 8.0]
    min_tp_points_vals = [5.0, 8.0]

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


def build_grid(strategy_id: str) -> List[Dict[str, Any]]:
    """Build grid for given strategy."""
    if strategy_id == "S1_TREND_EMA_ATR_ADX":
        return build_grid_s1()
    raise ValueError(f"Grid not defined for strategy: {strategy_id}")
