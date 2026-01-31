from __future__ import annotations

from itertools import product
from typing import Any, Dict, List, Literal


def build_grid_s1(preset: Literal["small", "medium", "large"] = "medium"):
    if preset == "small":
        ema_fast_vals = [20, 30]
        ema_slow_vals = [50, 100]

        adx_period_vals = [14]
        adx_th_vals = [20, 25]

        atr_period_vals = [14]

        k_sl_vals = [2.0, 3.0]
        k_tp_vals = [1.5]

        min_sl_points_vals = [5.0]
        min_tp_points_vals = [5.0]

    elif preset == "medium":
        ema_fast_vals = [10, 20, 30]
        ema_slow_vals = [50, 100]

        adx_period_vals = [10, 14, 20]
        adx_th_vals = [20, 25, 30]

        atr_period_vals = [10, 14, 20]

        k_sl_vals = [2.0, 3.0]
        k_tp_vals = [1.0, 1.5, 2.0]

        min_sl_points_vals = [5.0]
        min_tp_points_vals = [5.0]

    else:
        raise ValueError("Large preset not recommended yet")

    return [
        {
            "ema_fast": ef,
            "ema_slow": es,
            "adx_period": ap,
            "adx_th": ath,
            "atr_period": atrp,
            "k_sl": ksl,
            "k_tp": ktp,
            "min_sl_points": msl,
            "min_tp_points": mtp,
        }
        for ef, es, ap, ath, atrp, ksl, ktp, msl, mtp in product(
            ema_fast_vals,
            ema_slow_vals,
            adx_period_vals,
            adx_th_vals,
            atr_period_vals,
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

