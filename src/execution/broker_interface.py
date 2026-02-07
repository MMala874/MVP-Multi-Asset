from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Literal, Protocol


Side = Literal["BUY", "SELL"]


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: Side
    qty: float
    strategy_id: str
    timestamp: datetime


@dataclass(frozen=True)
class Fill:
    order_id: str
    symbol: str
    side: Side
    qty: float
    price: float
    timestamp: datetime
    strategy_id: str


class Broker(Protocol):
    def send_order(self, order: OrderRequest) -> Fill:
        """Send order to broker and return executed fill."""

    def get_positions(self) -> List[Dict[str, float | str]]:
        """Return current broker-side positions."""
