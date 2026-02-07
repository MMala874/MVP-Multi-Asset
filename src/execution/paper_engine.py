from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List

from src.execution.broker_interface import Broker, Fill, OrderRequest
from src.execution.logger import ExecutionLogger
from src.execution.risk_overlay import RiskOverlay


@dataclass(frozen=True)
class EngineState:
    cash: float
    positions: Dict[str, float]


class PaperBroker(Broker):
    """Deterministic paper broker for reproducible execution."""

    def __init__(self, *, starting_cash: float = 100_000.0, logger: ExecutionLogger | None = None) -> None:
        self.cash = float(starting_cash)
        self.positions: Dict[str, float] = {}
        self._order_seq = 1
        self.logger = logger

    def send_order(self, order: OrderRequest, *, price: float | None = None) -> Fill:
        if price is None:
            raise ValueError("PaperBroker.send_order requires explicit price for deterministic fills")

        order_id = f"paper-{self._order_seq}"
        self._order_seq += 1

        signed_qty = order.qty if order.side == "BUY" else -order.qty
        self.positions[order.symbol] = self.positions.get(order.symbol, 0.0) + signed_qty
        self.cash -= signed_qty * price

        fill = Fill(
            order_id=order_id,
            symbol=order.symbol,
            side=order.side,
            qty=order.qty,
            price=float(price),
            timestamp=order.timestamp,
            strategy_id=order.strategy_id,
        )

        if self.logger:
            self.logger.log("order_submitted", order, timestamp=order.timestamp)
            self.logger.log("order_filled", fill, timestamp=order.timestamp)
        return fill

    def get_positions(self) -> List[Dict[str, float | str]]:
        return [{"symbol": symbol, "qty": qty} for symbol, qty in sorted(self.positions.items())]

    def snapshot(self) -> EngineState:
        return EngineState(cash=self.cash, positions=dict(self.positions))


def run_orders(
    broker: PaperBroker,
    orders: List[OrderRequest],
    *,
    prices: Dict[str, float],
    equity: float,
    risk: RiskOverlay | None = None,
) -> List[Fill]:
    fills: List[Fill] = []
    for order in orders:
        if risk is not None:
            risk.evaluate(order, equity=equity, prices=prices, positions=broker.positions)
        fill = broker.send_order(order, price=float(prices[order.symbol]))
        fills.append(fill)
    return fills


def parity_check(backtest_fills: List[Fill], live_fills: List[Fill]) -> bool:
    """Check live/backtest parity by comparing deterministic fields only."""

    def normalize(fill: Fill) -> tuple:
        return (
            fill.symbol,
            fill.side,
            round(fill.qty, 8),
            round(fill.price, 8),
            fill.strategy_id,
        )

    return [normalize(f) for f in backtest_fills] == [normalize(f) for f in live_fills]


def build_order(symbol: str, side: str, qty: float, strategy_id: str, timestamp: datetime) -> OrderRequest:
    return OrderRequest(
        symbol=symbol,
        side=side,  # type: ignore[arg-type]
        qty=float(qty),
        strategy_id=strategy_id,
        timestamp=timestamp,
    )
