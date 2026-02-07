from __future__ import annotations

import json
from datetime import datetime

import pytest

from src.execution.paper_engine import PaperBroker, build_order, parity_check, run_orders
from src.execution.risk_overlay import RiskLimits, RiskOverlay
from src.execution.logger import ExecutionLogger


def test_paper_trading_is_reproducible() -> None:
    ts = datetime(2025, 1, 1, 10, 0, 0)
    orders = [build_order("EURUSD", "BUY", 1.5, "S1", ts), build_order("EURUSD", "SELL", 0.5, "S1", ts)]
    prices = {"EURUSD": 1.10}

    b1 = PaperBroker(starting_cash=10_000)
    b2 = PaperBroker(starting_cash=10_000)

    f1 = run_orders(b1, orders, prices=prices, equity=10_000)
    f2 = run_orders(b2, orders, prices=prices, equity=10_000)

    assert parity_check(f1, f2)
    assert b1.snapshot() == b2.snapshot()


def test_live_backtest_parity_check_detects_mismatch() -> None:
    ts = datetime(2025, 1, 1, 10, 0, 0)
    left = [build_order("EURUSD", "BUY", 1.0, "S1", ts)]
    right = [build_order("EURUSD", "BUY", 2.0, "S1", ts)]

    b1 = PaperBroker()
    b2 = PaperBroker()

    f1 = run_orders(b1, left, prices={"EURUSD": 1.2}, equity=100_000)
    f2 = run_orders(b2, right, prices={"EURUSD": 1.2}, equity=100_000)

    assert not parity_check(f1, f2)


def test_risk_overlay_drawdown_exposure_and_kill_switch() -> None:
    ts = datetime(2025, 1, 1, 10, 0, 0)
    broker = PaperBroker(starting_cash=10_000)
    risk = RiskOverlay(RiskLimits(max_drawdown_pct=0.10, max_symbol_exposure=100))

    with pytest.raises(RuntimeError, match="Exposure limit exceeded"):
        run_orders(
            broker,
            [build_order("EURUSD", "BUY", 200, "S1", ts)],
            prices={"EURUSD": 1.0},
            equity=10_000,
            risk=risk,
        )

    with pytest.raises(RuntimeError, match="Max drawdown exceeded"):
        run_orders(
            broker,
            [build_order("EURUSD", "BUY", 1, "S1", ts)],
            prices={"EURUSD": 1.0},
            equity=8_900,
            risk=risk,
        )

    risk.trigger_kill_switch()
    with pytest.raises(RuntimeError, match="Kill switch enabled"):
        run_orders(
            broker,
            [build_order("EURUSD", "BUY", 1, "S1", ts)],
            prices={"EURUSD": 1.0},
            equity=10_000,
            risk=risk,
        )


def test_execution_logger_writes_complete_jsonl(tmp_path) -> None:
    log_path = tmp_path / "execution.jsonl"
    logger = ExecutionLogger(log_path)
    broker = PaperBroker(logger=logger)
    ts = datetime(2025, 1, 1, 10, 0, 0)

    run_orders(
        broker,
        [build_order("EURUSD", "BUY", 1.0, "S1", ts)],
        prices={"EURUSD": 1.1111},
        equity=100_000,
    )

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    row0 = json.loads(lines[0])
    row1 = json.loads(lines[1])
    assert row0["event_type"] == "order_submitted"
    assert row1["event_type"] == "order_filled"
    assert row1["payload"]["price"] == 1.1111
