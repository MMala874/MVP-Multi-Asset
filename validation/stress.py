from __future__ import annotations

from copy import deepcopy
from typing import Dict


def _getattr(obj: object, name: str, default: object = None) -> object:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def apply_cost_stress(config: object, level: str) -> object:
    """Return a config copy with stressed costs using predefined scenarios."""
    stressed = deepcopy(config)
    costs = _getattr(stressed, "costs")
    if costs is None:
        raise ValueError("config.costs is required")
    scenarios: Dict[str, float] = _getattr(costs, "scenarios", {})
    if level not in scenarios:
        raise ValueError(f"Unknown cost stress level: {level}")
    multiplier = float(scenarios[level])

    spread = _getattr(costs, "spread_baseline_pips", {})
    if isinstance(spread, dict):
        for key, value in spread.items():
            spread[key] = float(value) * multiplier

    slippage = _getattr(costs, "slippage")
    if slippage is not None:
        slip_base = _getattr(slippage, "slip_base")
        slip_k = _getattr(slippage, "slip_k")
        if isinstance(slippage, dict):
            if slip_base is not None:
                slippage["slip_base"] = float(slip_base) * multiplier
            if slip_k is not None:
                slippage["slip_k"] = float(slip_k) * multiplier
        else:
            if slip_base is not None:
                setattr(slippage, "slip_base", float(slip_base) * multiplier)
            if slip_k is not None:
                setattr(slippage, "slip_k", float(slip_k) * multiplier)

    return stressed


def perturb_core_params(config: object, pct: float) -> object:
    """Perturb core strategy params by a percentage for robustness checks."""
    if pct <= 0:
        return deepcopy(config)
    perturbed = deepcopy(config)
    strategies = _getattr(perturbed, "strategies")
    params = _getattr(strategies, "params") if strategies is not None else None
    if not isinstance(params, dict):
        return perturbed

    seed = _getattr(_getattr(perturbed, "reproducibility"), "random_seed", 0)
    rng = _deterministic_rng(int(seed))

    for strategy_id, cfg in params.items():
        if not isinstance(cfg, dict):
            continue
        for key, value in list(cfg.items()):
            if isinstance(value, (int, float)):
                jitter = (rng.random() * 2 - 1) * pct
                cfg[key] = type(value)(value * (1 + jitter))
    return perturbed


def _deterministic_rng(seed: int):
    import random

    rng = random.Random(seed)
    return rng


__all__ = ["apply_cost_stress", "perturb_core_params"]
