from live.reconcile import reconcile_positions


def test_reconcile_detects_mismatch() -> None:
    expected_positions = [
        {"symbol": "EURUSD", "side": "LONG", "strategy_id": "s1", "qty": 1.5},
        {"symbol": "USDJPY", "side": "SHORT", "strategy_id": "s2", "qty": 2.0},
    ]
    broker_positions = [
        {"symbol": "EURUSD", "side": "LONG", "strategy_id": "s1", "qty": 1.0},
        {"symbol": "USDJPY", "side": "SHORT", "strategy_id": "s2", "qty": 2.0},
    ]

    ok, diffs = reconcile_positions(expected_positions, broker_positions)

    assert ok is False
    assert diffs
    assert diffs[0]["suggestion"] == "SAFE_MODE"
