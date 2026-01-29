from __future__ import annotations

from typing import List

from desk_types import Side, SignalIntent


def resolve_conflicts(
    signals: List[SignalIntent],
    policy: str,
    priority_order: List[str] | None,
) -> List[SignalIntent]:
    if policy == "priority":
        if not priority_order:
            return list(signals)
        return _resolve_priority(signals, priority_order)
    if policy == "netting":
        return _resolve_netting(signals)
    raise ValueError(f"Unknown conflict policy: {policy}")


def _resolve_priority(signals: List[SignalIntent], priority_order: List[str]) -> List[SignalIntent]:
    priority_map = {strategy_id: rank for rank, strategy_id in enumerate(priority_order)}
    by_symbol: dict[str, List[SignalIntent]] = {}
    for signal in signals:
        by_symbol.setdefault(signal.symbol, []).append(signal)

    filtered: List[SignalIntent] = []
    for symbol, symbol_signals in by_symbol.items():
        if len(symbol_signals) == 1:
            filtered.extend(symbol_signals)
            continue

        symbol_signals.sort(key=lambda item: priority_map.get(item.strategy_id, len(priority_map)))
        filtered.append(symbol_signals[0])

    return filtered


def _resolve_netting(signals: List[SignalIntent]) -> List[SignalIntent]:
    by_symbol: dict[str, List[SignalIntent]] = {}
    for signal in signals:
        by_symbol.setdefault(signal.symbol, []).append(signal)

    filtered: List[SignalIntent] = []
    for symbol, symbol_signals in by_symbol.items():
        sides = {signal.side for signal in symbol_signals}
        if len(sides) > 1 and Side.LONG in sides and Side.SHORT in sides:
            continue
        filtered.extend(symbol_signals)

    return filtered


__all__ = ["resolve_conflicts"]
