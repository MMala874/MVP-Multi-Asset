from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types" / "__init__.py"
_spec = importlib.util.spec_from_file_location("project_types", _TYPES_PATH)
_types_module = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("project_types", _types_module)
assert _spec and _spec.loader
_spec.loader.exec_module(_types_module)

Side = _types_module.Side
SignalIntent = _types_module.SignalIntent
OrderIntent = _types_module.OrderIntent
OrderType = _types_module.OrderType

__all__ = ["Side", "SignalIntent", "OrderIntent", "OrderType"]
