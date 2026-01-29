from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, TYPE_CHECKING

from risk._types import OrderIntent, OrderType, SignalIntent

if TYPE_CHECKING:
    from configs.models import Config


@dataclass
class AllocationState:
    prices: Dict[str, float]
    exposure_by_symbol: Dict[str, float]
    exposure_total: float
    risk_multiplier: float
    risk_multiplier_by_strategy: Dict[str, float]


def _build_state(state: object | None) -> AllocationState:
    if state is None:
        state_dict: Dict[str, object] = {}
    elif isinstance(state, dict):
        state_dict = state
    else:
        state_dict = state.__dict__

    prices = dict(state_dict.get("prices", {}))
    exposure_by_symbol = dict(state_dict.get("exposure_by_symbol", {}))
    exposure_total = float(state_dict.get("exposure_total", 0.0))
    risk_multiplier = float(state_dict.get("risk_multiplier", 1.0))
    risk_multiplier_by_strategy = dict(state_dict.get("risk_multiplier_by_strategy", {}))
    return AllocationState(
        prices=prices,
        exposure_by_symbol=exposure_by_symbol,
        exposure_total=exposure_total,
        risk_multiplier=risk_multiplier,
        risk_multiplier_by_strategy=risk_multiplier_by_strategy,
    )


class RiskAllocator:
    def __init__(self, config: "Config") -> None:
        self._config = config

    def allocate(self, signals: List[SignalIntent], state: object | None) -> List[OrderIntent]:
        caps = self._config.risk.caps
        state_view = _build_state(state)
        allocated: List[OrderIntent] = []
        risk_by_strategy: Dict[str, float] = {}
        risk_by_symbol: Dict[str, float] = {}
        exposure_total = state_view.exposure_total

        for signal in signals:
            if signal.sl_points is None:
                continue
            if signal.sl_points <= 0:
                continue

            risk_multiplier = _resolve_risk_multiplier(signal, state_view)
            risk_amount = self._config.risk.r_base * risk_multiplier
            if risk_amount <= 0:
                continue

            sl_distance_value = signal.sl_points
            qty = risk_amount / sl_distance_value

            if not _within_caps(
                signal,
                risk_amount,
                qty,
                risk_by_strategy,
                risk_by_symbol,
                caps.per_strategy,
                caps.per_symbol,
                caps.usd_exposure_cap,
                state_view,
                exposure_total,
            ):
                continue

            order = OrderIntent(
                strategy_id=signal.strategy_id,
                symbol=signal.symbol,
                side=signal.side,
                order_type=OrderType.MARKET,
                qty=qty,
                created_time=datetime.utcnow(),
                sl_points=signal.sl_points,
                tp_points=signal.tp_points,
                meta={"risk_multiplier": f"{risk_multiplier:.4f}"},
            )
            allocated.append(order)
            risk_by_strategy[signal.strategy_id] = risk_by_strategy.get(signal.strategy_id, 0.0) + risk_amount
            risk_by_symbol[signal.symbol] = risk_by_symbol.get(signal.symbol, 0.0) + risk_amount
            exposure_total += _estimate_usd_exposure(qty, signal.symbol, state_view)

        return allocated


def _resolve_risk_multiplier(signal: SignalIntent, state_view: AllocationState) -> float:
    tag_value = signal.tags.get("risk_multiplier")
    if tag_value is not None:
        try:
            return float(tag_value)
        except ValueError:
            return state_view.risk_multiplier

    if signal.strategy_id in state_view.risk_multiplier_by_strategy:
        return float(state_view.risk_multiplier_by_strategy[signal.strategy_id])

    return state_view.risk_multiplier


def _estimate_usd_exposure(qty: float, symbol: str, state_view: AllocationState) -> float:
    price = float(state_view.prices.get(symbol, 1.0))
    return abs(qty) * price


def _within_caps(
    signal: SignalIntent,
    risk_amount: float,
    qty: float,
    risk_by_strategy: Dict[str, float],
    risk_by_symbol: Dict[str, float],
    per_strategy_cap: float,
    per_symbol_cap: float,
    usd_exposure_cap: float,
    state_view: AllocationState,
    exposure_total: float,
) -> bool:
    next_strategy = risk_by_strategy.get(signal.strategy_id, 0.0) + risk_amount
    if next_strategy > per_strategy_cap:
        return False

    next_symbol = risk_by_symbol.get(signal.symbol, 0.0) + risk_amount
    if next_symbol > per_symbol_cap:
        return False

    next_exposure_total = exposure_total + _estimate_usd_exposure(qty, signal.symbol, state_view)
    if next_exposure_total > usd_exposure_cap:
        return False

    return True


__all__ = ["RiskAllocator"]
