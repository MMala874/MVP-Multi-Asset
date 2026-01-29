from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest

from desk_types import (
    Fill,
    OrderIntent,
    OrderType,
    Position,
    Scenario,
    Side,
    SignalIntent,
    SystemState,
)


def _sample_datetime() -> datetime:
    return datetime(2024, 1, 2, 3, 4, 5)


def test_signal_intent_roundtrip():
    original = SignalIntent(
        strategy_id="strat-1",
        symbol="EURUSD",
        side=Side.LONG,
        signal_time=_sample_datetime(),
        sl_points=12.5,
        tp_points=25.0,
        tags={"regime": "trend", "reason": "breakout"},
    )
    payload = original.to_dict()
    restored = SignalIntent.from_dict(payload)
    assert restored == original


def test_order_intent_roundtrip():
    original = OrderIntent(
        strategy_id="strat-2",
        symbol="USDJPY",
        side=Side.SHORT,
        order_type=OrderType.LIMIT,
        qty=1.25,
        created_time=_sample_datetime(),
        sl_points=None,
        tp_points=30.0,
        meta={"client": "desk"},
    )
    payload = original.to_dict()
    restored = OrderIntent.from_dict(payload)
    assert restored == original


def test_fill_roundtrip():
    original = Fill(
        order_id="order-99",
        symbol="GBPUSD",
        side=Side.LONG,
        qty=3.5,
        fill_time=_sample_datetime(),
        fill_price=1.2345,
        spread_pips=0.2,
        slippage_pips=-0.1,
        scenario=Scenario.B,
        meta={"venue": "sim"},
    )
    payload = original.to_dict()
    restored = Fill.from_dict(payload)
    assert restored == original


def test_position_roundtrip():
    original = Position(
        position_id="pos-7",
        symbol="XAUUSD",
        side=Side.FLAT,
        qty=0.0,
        avg_price=0.0,
        open_time=_sample_datetime(),
        strategy_id="strat-3",
        magic_number=42,
        meta={"note": "closed"},
    )
    payload = original.to_dict()
    restored = Position.from_dict(payload)
    assert restored == original


@pytest.mark.parametrize(
    "instance,field, value",
    [
        (
            SignalIntent(
                strategy_id="strat-1",
                symbol="EURUSD",
                side=Side.LONG,
                signal_time=_sample_datetime(),
                sl_points=None,
                tp_points=None,
                tags={},
            ),
            "symbol",
            "USDCHF",
        ),
        (
            OrderIntent(
                strategy_id="strat-2",
                symbol="USDJPY",
                side=Side.SHORT,
                order_type=OrderType.MARKET,
                qty=1.0,
                created_time=_sample_datetime(),
                sl_points=None,
                tp_points=None,
                meta={},
            ),
            "qty",
            2.0,
        ),
        (
            Fill(
                order_id="order-99",
                symbol="GBPUSD",
                side=Side.LONG,
                qty=3.5,
                fill_time=_sample_datetime(),
                fill_price=1.2345,
                spread_pips=0.2,
                slippage_pips=-0.1,
                scenario=Scenario.A,
                meta={},
            ),
            "fill_price",
            1.5,
        ),
        (
            Position(
                position_id="pos-7",
                symbol="XAUUSD",
                side=Side.FLAT,
                qty=0.0,
                avg_price=0.0,
                open_time=_sample_datetime(),
                strategy_id="strat-3",
                magic_number=42,
                meta={},
            ),
            "magic_number",
            99,
        ),
    ],
)
def test_dataclasses_are_frozen(instance, field, value):
    with pytest.raises(FrozenInstanceError):
        setattr(instance, field, value)


@pytest.mark.parametrize(
    "enum_type, invalid_value",
    [
        (Side, "BULL"),
        (OrderType, "IOC"),
        (Scenario, "D"),
        (SystemState, "BROKEN"),
    ],
)
def test_enums_reject_invalid_values(enum_type, invalid_value):
    with pytest.raises(ValueError):
        enum_type(invalid_value)
