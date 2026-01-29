from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
from pandas.testing import assert_frame_equal

from monitoring.strategy_health import compute_health_metrics


def _sample_trades() -> pd.DataFrame:
    base_time = datetime(2024, 1, 1, 0, 0, 0)
    rows = [
        {
            "strategy_id": "S1",
            "pnl": 10.0,
            "pnl_pct": 0.01,
            "signal_time": base_time,
        },
        {
            "strategy_id": "S1",
            "pnl": -5.0,
            "pnl_pct": -0.005,
            "signal_time": base_time + timedelta(minutes=5),
        },
        {
            "strategy_id": "S2",
            "pnl": 7.0,
            "pnl_pct": 0.008,
            "signal_time": base_time + timedelta(minutes=10),
        },
    ]
    return pd.DataFrame(rows)


def test_flags_present() -> None:
    trades_df = _sample_trades()
    metrics = compute_health_metrics(trades_df, window=2)
    assert set(metrics.keys()) == {"S1", "S2"}
    for data in metrics.values():
        assert data["flag"] in {"OK", "WEAKENING", "OUT_OF_PROFILE"}


def test_no_side_effects() -> None:
    trades_df = _sample_trades()
    original_df = trades_df.copy(deep=True)
    reference_stats = {"S1": {"win_rate": 0.6, "avg_pnl": 1.5}}
    reference_copy = {"S1": {"win_rate": 0.6, "avg_pnl": 1.5}}

    _ = compute_health_metrics(trades_df, reference_stats=reference_stats, window=2)

    assert_frame_equal(trades_df, original_df)
    assert reference_stats == reference_copy
