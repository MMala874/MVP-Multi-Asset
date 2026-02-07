from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


class ExecutionLogger:
    """JSONL execution logger for complete order/fill/risk audit trail."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event_type: str, payload: Any, *, timestamp: datetime | None = None) -> None:
        event = {
            "timestamp": (timestamp or datetime.utcnow()).isoformat(),
            "event_type": event_type,
            "payload": self._normalize(payload),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, default=str) + "\n")

    @staticmethod
    def _normalize(payload: Any) -> Dict[str, Any] | Any:
        if is_dataclass(payload):
            return asdict(payload)
        if isinstance(payload, dict):
            return payload
        if hasattr(payload, "__dict__"):
            return vars(payload)
        return payload
