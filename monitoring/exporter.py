from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def export_snapshot(snapshot: Dict[str, Any], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    return target
