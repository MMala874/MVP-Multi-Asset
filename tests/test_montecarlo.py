import random

from montecarlo.mc1_block_bootstrap import _block_bootstrap_sample, run_block_bootstrap
from montecarlo.mc2_cost_noise import run_cost_noise


def test_seed_determinism():
    trade_pnls = [1.0, -0.5, 0.25, -0.75, 1.5]
    result_a = run_block_bootstrap(trade_pnls, block_min=2, block_max=3, n_sims=5, seed=42)
    result_b = run_block_bootstrap(trade_pnls, block_min=2, block_max=3, n_sims=5, seed=42)
    assert result_a == result_b

    trades_pre_cost = [
        {"pnl_pre_cost": 1.0, "spread_cost": 0.1, "slippage_cost": 0.05, "is_spike": False},
        {"pnl_pre_cost": -0.5, "spread_cost": 0.1, "slippage_cost": 0.08, "is_spike": True},
        {"pnl_pre_cost": 0.75, "spread_cost": 0.1, "slippage_cost": 0.03, "is_spike": False},
    ]
    noise_params = {
        "spread_mult_range": (0.8, 1.2),
        "slippage_mult_range": (0.7, 1.3),
        "spike_slippage_mult_range": (1.2, 1.8),
    }
    result_c = run_cost_noise(trades_pre_cost, cost_model=None, noise_params=noise_params, n_sims=10, seed=7)
    result_d = run_cost_noise(trades_pre_cost, cost_model=None, noise_params=noise_params, n_sims=10, seed=7)
    assert result_c == result_d


def test_block_bootstrap_preserves_structure():
    trade_pnls = [float(i) for i in range(10)]
    rng = random.Random(123)
    sample = _block_bootstrap_sample(trade_pnls, block_min=3, block_max=3, rng=rng)

    original_pairs = {(trade_pnls[i], trade_pnls[i + 1]) for i in range(len(trade_pnls) - 1)}
    adjacency_count = sum(
        1
        for i in range(len(sample) - 1)
        if (sample[i], sample[i + 1]) in original_pairs
    )

    assert adjacency_count >= 6


def test_cost_noise_changes_distribution():
    trades_pre_cost = [
        {"pnl_pre_cost": 1.0, "spread_cost": 0.1, "slippage_cost": 0.05, "is_spike": False},
        {"pnl_pre_cost": -0.5, "spread_cost": 0.1, "slippage_cost": 0.08, "is_spike": True},
        {"pnl_pre_cost": 0.75, "spread_cost": 0.1, "slippage_cost": 0.03, "is_spike": False},
        {"pnl_pre_cost": 0.2, "spread_cost": 0.1, "slippage_cost": 0.04, "is_spike": True},
    ]
    noise_params = {
        "spread_mult_range": (0.8, 1.2),
        "slippage_mult_range": (0.7, 1.3),
        "spike_slippage_mult_range": (1.2, 1.8),
    }

    result = run_cost_noise(trades_pre_cost, cost_model=None, noise_params=noise_params, n_sims=50, seed=99)
    rounded = {round(value, 6) for value in result["pnl_distribution"]}

    assert len(rounded) > 1
