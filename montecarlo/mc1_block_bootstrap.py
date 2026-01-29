from __future__ import annotations

import math
import random
from typing import Sequence


def _block_bootstrap_sample(
    trade_pnls: Sequence[float],
    block_min: int,
    block_max: int,
    rng: random.Random,
) -> list[float]:
    if block_min <= 0 or block_max <= 0:
        raise ValueError("block_min and block_max must be positive")
    if block_min > block_max:
        raise ValueError("block_min must be <= block_max")

    n = len(trade_pnls)
    if n == 0:
        return []

    sample: list[float] = []
    while len(sample) < n:
        block_len = rng.randint(block_min, block_max)
        start = rng.randrange(0, n)
        for offset in range(block_len):
            sample.append(trade_pnls[(start + offset) % n])
            if len(sample) >= n:
                break
    return sample


def _max_drawdown_and_recovery(pnls: Sequence[float]) -> tuple[float, int]:
    equity = 0.0
    peak = 0.0
    peak_index = 0
    max_dd = 0.0
    max_recovery = 0
    in_drawdown = False

    for idx, pnl in enumerate(pnls):
        equity += float(pnl)
        if equity >= peak:
            if in_drawdown:
                max_recovery = max(max_recovery, idx - peak_index)
                in_drawdown = False
            peak = equity
            peak_index = idx
        else:
            in_drawdown = True
            max_dd = max(max_dd, peak - equity)

    if in_drawdown:
        max_recovery = max(max_recovery, len(pnls) - 1 - peak_index)

    return max_dd, max_recovery


def _percentile(sorted_values: Sequence[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if pct <= 0:
        return sorted_values[0]
    if pct >= 1:
        return sorted_values[-1]
    idx = int(math.ceil(pct * len(sorted_values)) - 1)
    idx = max(0, min(idx, len(sorted_values) - 1))
    return sorted_values[idx]


def run_block_bootstrap(
    trade_pnls: Sequence[float],
    block_min: int,
    block_max: int,
    n_sims: int,
    seed: int,
) -> dict:
    rng = random.Random(seed)
    pnls_list = list(trade_pnls)
    if n_sims <= 0:
        raise ValueError("n_sims must be positive")

    baseline_peak = 0.0
    equity = 0.0
    for pnl in pnls_list:
        equity += float(pnl)
        baseline_peak = max(baseline_peak, equity)
    dd_threshold = 0.1 * max(1.0, baseline_peak)

    max_drawdowns: list[float] = []
    recoveries: list[int] = []

    for _ in range(n_sims):
        sample = _block_bootstrap_sample(pnls_list, block_min, block_max, rng)
        max_dd, max_rec = _max_drawdown_and_recovery(sample)
        max_drawdowns.append(max_dd)
        recoveries.append(max_rec)

    prob_dd_gt_threshold = sum(1 for dd in max_drawdowns if dd > dd_threshold) / n_sims
    sorted_dds = sorted(max_drawdowns)
    worst_1pct = _percentile(sorted_dds, 0.99)

    return {
        "max_drawdowns": max_drawdowns,
        "prob_dd_gt_threshold": prob_dd_gt_threshold,
        "dd_threshold": dd_threshold,
        "time_to_recovery": recoveries,
        "worst_1pct": worst_1pct,
    }
