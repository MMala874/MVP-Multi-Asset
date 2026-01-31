from __future__ import annotations

from itertools import product
from typing import Any, Dict, List, Literal


def build_grid_s1(preset: Literal["small", "medium", "large"] = "medium") -> List[Dict[str, Any]]:
    if preset == "small":
        # Keep fixed (for now)
        ema_fast_vals = [30]
        ema_slow_vals = [100]
        adx_period_vals = [14]
        atr_period_vals = [14]

        # Breakout + filters
        breakout_lookback_vals = [20, 55, 100]
        buffer_atr_vals = [0.0, 0.1, 0.2]
        adx_th_vals = [20, 25, 30]
        cooldown_bars_vals = [0, 8, 16]

        # Risk geometry
        k_sl_vals = [2.0, 2.5, 3.0]
        k_tp_vals = [1.0, 1.5, 2.0]
        min_sl_points_vals = [8.0]
        min_tp_points_vals = [5.0]

        # Optional gates (keep fixed for now)
        allowed_vol_regimes_vals = [["MID", "HIGH"]]
        spike_block_vals = [False]
        adx_rising_vals = [False]

    elif preset == "medium":
        # Slightly wider but still sane
        ema_fast_vals = [20, 30, 40]
        ema_slow_vals = [80, 100, 150]
        adx_period_vals = [14]
        atr_period_vals = [14]

        breakout_lookback_vals = [20, 55, 100]
        buffer_atr_vals = [0.0, 0.1, 0.2]
        adx_th_vals = [20, 25, 30]
        cooldown_bars_vals = [0, 8, 16]

        k_sl_vals = [2.0, 2.5, 3.0]
        k_tp_vals = [1.0, 1.5, 2.0]
        min_sl_points_vals = [8.0]
        min_tp_points_vals = [5.0]

        allowed_vol_regimes_vals = [["MID", "HIGH"]]
        spike_block_vals = [False]
        adx_rising_vals = [False]

    else:
        raise ValueError("Large preset not recommended yet")

    grid = []
    for (
        ef, es, adxp, atrp,
        bl, ba, ath, cd,
        ksl, ktp, msl, mtp,
        avr, spk, ar
    ) in product(
        ema_fast_vals,
        ema_slow_vals,
        adx_period_vals,
        atr_period_vals,
        breakout_lookback_vals,
        buffer_atr_vals,
        adx_th_vals,
        cooldown_bars_vals,
        k_sl_vals,
        k_tp_vals,
        min_sl_points_vals,
        min_tp_points_vals,
        allowed_vol_regimes_vals,
        spike_block_vals,
        adx_rising_vals,
    ):
        grid.append({
            "ema_fast": ef,
            "ema_slow": es,
            "adx_period": adxp,
            "adx_th": ath,
            "atr_period": atrp,
            "breakout_lookback": bl,
            "buffer_atr": ba,
            "cooldown_bars": cd,
            "k_sl": ksl,
            "k_tp": ktp,
            "min_sl_points": msl,
            "min_tp_points": mtp,
            "allowed_vol_regimes": avr,
            "spike_block": spk,
            "adx_rising": ar,
        })

    return grid


def build_grid(strategy_id: str, preset: Literal["small", "medium", "large"] = "medium") -> List[Dict[str, Any]]:
    if strategy_id == "S1_TREND_BREAKOUT_DONCHIAN":
        return build_grid_s1(preset)
    raise ValueError(f"Grid not defined for strategy: {strategy_id}")
