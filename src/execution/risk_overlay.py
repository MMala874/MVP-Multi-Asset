from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from src.execution.broker_interface import OrderRequest


@dataclass
class RiskLimits:
    max_drawdown_pct: float
    max_symbol_exposure: float


class RiskOverlay:
    """Runtime risk guard with drawdown checks, exposure limits, and kill switch."""

    def __init__(self, limits: RiskLimits) -> None:
        self.limits = limits
        self.peak_equity: Optional[float] = None
        self.kill_switch = False

    def evaluate(self, order: OrderRequest, *, equity: float, prices: Dict[str, float], positions: Dict[str, float]) -> None:
        if self.kill_switch:
            raise RuntimeError("Kill switch enabled")

        self._update_peak_equity(equity)
        self._check_drawdown(equity)
        self._check_exposure(order, prices, positions)

    def trigger_kill_switch(self) -> None:
        self.kill_switch = True

    def _update_peak_equity(self, equity: float) -> None:
        if self.peak_equity is None:
            self.peak_equity = equity
        else:
            self.peak_equity = max(self.peak_equity, equity)

    def _check_drawdown(self, equity: float) -> None:
        assert self.peak_equity is not None
        if self.peak_equity <= 0:
            return
        dd_pct = (self.peak_equity - equity) / self.peak_equity
        if dd_pct > self.limits.max_drawdown_pct:
            raise RuntimeError(f"Max drawdown exceeded: {dd_pct:.4f}")

    def _check_exposure(self, order: OrderRequest, prices: Dict[str, float], positions: Dict[str, float]) -> None:
        px = float(prices[order.symbol])
        current_qty = float(positions.get(order.symbol, 0.0))
        signed_qty = order.qty if order.side == "BUY" else -order.qty
        projected_notional = abs((current_qty + signed_qty) * px)
        if projected_notional > self.limits.max_symbol_exposure:
            raise RuntimeError(
                f"Exposure limit exceeded for {order.symbol}: {projected_notional:.2f} > {self.limits.max_symbol_exposure:.2f}"
            )
