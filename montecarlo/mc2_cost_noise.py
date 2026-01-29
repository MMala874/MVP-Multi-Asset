from __future__ import annotations

import math
import random
from typing import Iterable, Mapping, Sequence


def _get_cost_model_params(cost_model: object | None) -> tuple[float, float, float]:
    if cost_model is None:
        return 1.0, 1.0, 0.0
    if isinstance(cost_model, Mapping):
        return (
            float(cost_model.get("spread_mult", 1.0)),
            float(cost_model.get("slippage_mult", 1.0)),
            float(cost_model.get("slippage_add", 0.0)),
        )
    spread_mult = float(getattr(cost_model, "spread_mult", 1.0))
    slippage_mult = float(getattr(cost_model, "slippage_mult", 1.0))
    slippage_add = float(getattr(cost_model, "slippage_add", 0.0))
    return spread_mult, slippage_mult, slippage_add


def _get_noise_range(noise_params: Mapping[str, object], key: str, default: tuple[float, float]) -> tuple[float, float]:
    value = noise_params.get(key, default)
    if isinstance(value, Sequence) and len(value) == 2:
        return float(value[0]), float(value[1])
    return default


def _apply_cost_noise(
    trades_pre_cost: Sequence[Mapping[str, object]],
    cost_model: object | None,
    noise_params: Mapping[str, object],
    rng: random.Random,
) -> list[float]:
    spread_mult_base, slippage_mult_base, slippage_add = _get_cost_model_params(cost_model)
    spread_range = _get_noise_range(noise_params, "spread_mult_range", (1.0, 1.0))
    slippage_range = _get_noise_range(noise_params, "slippage_mult_range", (1.0, 1.0))
    spike_range = _get_noise_range(noise_params, "spike_slippage_mult_range", (1.0, 1.0))

    pnls_post_cost: list[float] = []
    for trade in trades_pre_cost:
        pnl_pre_cost = float(trade.get("pnl_pre_cost", trade.get("pnl", 0.0)))
        spread_cost = float(trade.get("spread_cost", 0.0))
        slippage_cost = float(trade.get("slippage_cost", 0.0))
        is_spike = bool(trade.get("is_spike", False))

        spread_mult = rng.uniform(*spread_range)
        slippage_mult = rng.uniform(*slippage_range)
        if is_spike:
            slippage_mult *= rng.uniform(*spike_range)

        cost = spread_cost * spread_mult_base * spread_mult
        cost += slippage_cost * slippage_mult_base * slippage_mult
        cost += slippage_add
        pnls_post_cost.append(pnl_pre_cost - cost)

    return pnls_post_cost


def _mean(values: Iterable[float]) -> float:
    vals = list(values)
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


def _stdev(values: Iterable[float], mean: float) -> float:
    vals = list(values)
    if len(vals) < 2:
        return 0.0
    variance = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
    return math.sqrt(variance)


def run_cost_noise(
    trades_pre_cost: Sequence[Mapping[str, object]],
    cost_model: object | None,
    noise_params: Mapping[str, object],
    n_sims: int,
    seed: int,
) -> dict:
    if n_sims <= 0:
        raise ValueError("n_sims must be positive")
    rng = random.Random(seed)

    pnl_distribution: list[float] = []
    for _ in range(n_sims):
        pnls_post_cost = _apply_cost_noise(trades_pre_cost, cost_model, noise_params, rng)
        pnl_distribution.append(sum(pnls_post_cost))

    mean_pnl = _mean(pnl_distribution)
    stdev_pnl = _stdev(pnl_distribution, mean_pnl)

    return {
        "pnl_distribution": pnl_distribution,
        "mean_pnl": mean_pnl,
        "stdev_pnl": stdev_pnl,
    }
