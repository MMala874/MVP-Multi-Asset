from __future__ import annotations

from typing import Dict, List

import pandas as pd

from validation.filter_tuner import FilterTuner


def _base_config() -> Dict[str, object]:
    return {
        "validation": {"walk_forward": {"train": 4, "val": 4, "test": 4}},
        "costs": {
            "spread_baseline_pips": {"EURUSD": 1.0},
            "slippage": {"slip_base": 0.0, "slip_k": 0.0},
            "scenarios": {"A": 1.0, "B": 1.5, "C": 2.0},
        },
    }


def test_tuner_search_space_limit() -> None:
    tuner = FilterTuner()
    for strategy_id in (
        "S1_TREND_EMA_ATR_ADX",
        "S2_MR_ZSCORE_EMA_REGIME",
        "S3_BREAKOUT_ATR_REGIME_EMA200",
    ):
        space = tuner._build_search_space(strategy_id)
        assert len(space) <= 800


def test_no_test_leakage_selection() -> None:
    index = pd.date_range("2024-01-01", periods=12, freq="D")
    df = pd.DataFrame(
        {
            "pnl": [-1, -1, -1, -1, -1, -1, 2, 2, 10, 10, -1, -1],
            "adx": [5, 5, 5, 5, 10, 10, 30, 30, 5, 5, 30, 30],
            "atr_pct": [0.2] * 12,
        },
        index=index,
    )
    df_by_symbol = {"EURUSD": df}

    class _TestTuner(FilterTuner):
        def _build_search_space(self, strategy_id: str) -> List[Dict[str, float]]:
            return [
                {"adx_th": 5.0, "min_atr_pct": 0.0},
                {"adx_th": 25.0, "min_atr_pct": 0.0},
            ]

    tuner = _TestTuner(top_k=1)
    results = tuner.tune("S1_TREND_EMA_ATR_ADX", _base_config(), df_by_symbol)
    assert results
    assert results[0]["params"]["adx_th"] == 25.0


def test_score_monotonic_penalties() -> None:
    tuner = FilterTuner()
    base = tuner._score(expectancy=1.0, max_dd=-0.5, dd_duration=2.0, cost_sensitivity=0.1)
    worse_dd = tuner._score(expectancy=1.0, max_dd=-1.0, dd_duration=2.0, cost_sensitivity=0.1)
    worse_duration = tuner._score(expectancy=1.0, max_dd=-0.5, dd_duration=5.0, cost_sensitivity=0.1)
    assert worse_dd < base
    assert worse_duration < base
