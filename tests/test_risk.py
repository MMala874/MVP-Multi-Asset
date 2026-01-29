from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from risk.allocator import RiskAllocator
from risk.conflict import resolve_conflicts
from risk._types import Side, SignalIntent


def _signal(strategy_id: str, symbol: str, side: Side, sl_points: float | None) -> SignalIntent:
    return SignalIntent(
        strategy_id=strategy_id,
        symbol=symbol,
        side=side,
        signal_time=datetime(2024, 1, 1, 0, 0, 0),
        sl_points=sl_points,
        tp_points=None,
        tags={},
    )


def _allocator(r_base: float, per_strategy: float, per_symbol: float, usd_cap: float) -> RiskAllocator:
    caps = SimpleNamespace(
        per_strategy=per_strategy,
        per_symbol=per_symbol,
        usd_exposure_cap=usd_cap,
    )
    risk = SimpleNamespace(r_base=r_base, caps=caps)
    config = SimpleNamespace(risk=risk)
    return RiskAllocator(config)


def test_conflict_priority() -> None:
    signals = [
        _signal("S1", "EURUSD", Side.LONG, 10.0),
        _signal("S2", "EURUSD", Side.SHORT, 12.0),
    ]
    filtered = resolve_conflicts(signals, policy="priority", priority_order=["S2", "S1"])
    assert len(filtered) == 1
    assert filtered[0].strategy_id == "S2"
    assert filtered[0].side == Side.SHORT


def test_caps_applied() -> None:
    allocator = _allocator(r_base=0.01, per_strategy=0.01, per_symbol=0.02, usd_cap=100000)
    signals = [
        _signal("S1", "EURUSD", Side.LONG, 10.0),
        _signal("S1", "EURUSD", Side.LONG, 10.0),
    ]
    orders = allocator.allocate(signals, state=None)
    assert len(orders) == 1


def test_allocator_no_order_without_sl() -> None:
    allocator = _allocator(r_base=0.01, per_strategy=0.05, per_symbol=0.05, usd_cap=100000)
    signals = [_signal("S1", "EURUSD", Side.LONG, None)]
    orders = allocator.allocate(signals, state=None)
    assert orders == []
