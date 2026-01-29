"""Type definitions for a systematic trading desk."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class OrderType(str, Enum):
    MARKET = "MARKET"
    STOP = "STOP"
    LIMIT = "LIMIT"


class Scenario(str, Enum):
    A = "A"
    B = "B"
    C = "C"


class SystemState(str, Enum):
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    SAFE_MODE = "SAFE_MODE"
    HALTED = "HALTED"


def _serialize_datetime(value: datetime) -> str:
    return value.isoformat()


def _deserialize_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass(frozen=True)
class SignalIntent:
    strategy_id: str
    symbol: str
    side: Side
    signal_time: datetime
    sl_points: Optional[float]
    tp_points: Optional[float]
    tags: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "signal_time": _serialize_datetime(self.signal_time),
            "sl_points": self.sl_points,
            "tp_points": self.tp_points,
            "tags": dict(self.tags),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SignalIntent":
        return cls(
            strategy_id=data["strategy_id"],
            symbol=data["symbol"],
            side=Side(data["side"]),
            signal_time=_deserialize_datetime(data["signal_time"]),
            sl_points=data.get("sl_points"),
            tp_points=data.get("tp_points"),
            tags=dict(data.get("tags", {})),
        )


@dataclass(frozen=True)
class OrderIntent:
    strategy_id: str
    symbol: str
    side: Side
    order_type: OrderType
    qty: float
    created_time: datetime
    sl_points: Optional[float]
    tp_points: Optional[float]
    meta: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "qty": self.qty,
            "created_time": _serialize_datetime(self.created_time),
            "sl_points": self.sl_points,
            "tp_points": self.tp_points,
            "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OrderIntent":
        return cls(
            strategy_id=data["strategy_id"],
            symbol=data["symbol"],
            side=Side(data["side"]),
            order_type=OrderType(data["order_type"]),
            qty=float(data["qty"]),
            created_time=_deserialize_datetime(data["created_time"]),
            sl_points=data.get("sl_points"),
            tp_points=data.get("tp_points"),
            meta=dict(data.get("meta", {})),
        )


@dataclass(frozen=True)
class Fill:
    order_id: str
    symbol: str
    side: Side
    qty: float
    fill_time: datetime
    fill_price: float
    spread_pips: float
    slippage_pips: float
    scenario: Scenario
    meta: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "qty": self.qty,
            "fill_time": _serialize_datetime(self.fill_time),
            "fill_price": self.fill_price,
            "spread_pips": self.spread_pips,
            "slippage_pips": self.slippage_pips,
            "scenario": self.scenario.value,
            "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Fill":
        return cls(
            order_id=data["order_id"],
            symbol=data["symbol"],
            side=Side(data["side"]),
            qty=float(data["qty"]),
            fill_time=_deserialize_datetime(data["fill_time"]),
            fill_price=float(data["fill_price"]),
            spread_pips=float(data["spread_pips"]),
            slippage_pips=float(data["slippage_pips"]),
            scenario=Scenario(data["scenario"]),
            meta=dict(data.get("meta", {})),
        )


@dataclass(frozen=True)
class Position:
    position_id: str
    symbol: str
    side: Side
    qty: float
    avg_price: float
    open_time: datetime
    strategy_id: str
    magic_number: int
    meta: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position_id": self.position_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "qty": self.qty,
            "avg_price": self.avg_price,
            "open_time": _serialize_datetime(self.open_time),
            "strategy_id": self.strategy_id,
            "magic_number": self.magic_number,
            "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Position":
        return cls(
            position_id=data["position_id"],
            symbol=data["symbol"],
            side=Side(data["side"]),
            qty=float(data["qty"]),
            avg_price=float(data["avg_price"]),
            open_time=_deserialize_datetime(data["open_time"]),
            strategy_id=data["strategy_id"],
            magic_number=int(data["magic_number"]),
            meta=dict(data.get("meta", {})),
        )


__all__ = [
    "Side",
    "OrderType",
    "Scenario",
    "SystemState",
    "SignalIntent",
    "OrderIntent",
    "Fill",
    "Position",
]
