from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple


def reconcile_positions(
    expected_positions: Iterable[Any],
    broker_positions: Iterable[Any],
    *,
    qty_tolerance: float = 1e-6,
) -> Tuple[bool, List[Dict[str, Any]]]:
    expected = _aggregate_positions(expected_positions)
    broker = _aggregate_positions(broker_positions)

    diffs: List[Dict[str, Any]] = []
    keys = set(expected.keys()) | set(broker.keys())

    for key in sorted(keys):
        expected_qty = expected.get(key, 0.0)
        broker_qty = broker.get(key, 0.0)
        if abs(expected_qty - broker_qty) > qty_tolerance:
            diffs.append(
                {
                    "key": key,
                    "expected_qty": expected_qty,
                    "broker_qty": broker_qty,
                    "suggestion": "SAFE_MODE",
                }
            )

    return len(diffs) == 0, diffs


def _aggregate_positions(positions: Iterable[Any]) -> Dict[tuple, float]:
    aggregated: Dict[tuple, float] = {}
    for position in positions:
        payload = _normalize_position(position)
        key = (payload["symbol"], payload["side"], payload["strategy_id"])
        aggregated[key] = aggregated.get(key, 0.0) + float(payload["qty"])
    return aggregated


def _normalize_position(position: Any) -> Dict[str, Any]:
    if hasattr(position, "to_dict"):
        payload = position.to_dict()
    elif isinstance(position, dict):
        payload = position
    else:
        payload = position.__dict__

    side = payload.get("side")
    if hasattr(side, "value"):
        side = side.value

    return {
        "symbol": payload.get("symbol"),
        "side": side,
        "strategy_id": payload.get("strategy_id", ""),
        "qty": payload.get("qty", 0.0),
    }


__all__ = ["reconcile_positions"]
