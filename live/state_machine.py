from __future__ import annotations

from pathlib import Path
import importlib.util
import sys

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types" / "__init__.py"
_spec = importlib.util.spec_from_file_location("project_types", _TYPES_PATH)
_types_module = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("project_types", _types_module)
assert _spec and _spec.loader
_spec.loader.exec_module(_types_module)

SystemState = _types_module.SystemState


class SystemStateMachine:
    def __init__(self, max_execution_errors: int) -> None:
        self._state = SystemState.RUNNING
        self._max_execution_errors = max_execution_errors
        self._execution_errors = 0

    @property
    def state(self) -> SystemState:
        return self._state

    @property
    def execution_errors(self) -> int:
        return self._execution_errors

    def record_execution_error(self) -> SystemState:
        self._execution_errors += 1
        if self._execution_errors >= self._max_execution_errors:
            self._state = SystemState.HALTED
        elif self._state == SystemState.RUNNING:
            self._state = SystemState.DEGRADED
        return self._state

    def record_reconcile_mismatch(self) -> SystemState:
        if self._state != SystemState.HALTED:
            self._state = SystemState.SAFE_MODE
        return self._state

    def record_dd_flags(self, *, day_dd_breached: bool, week_dd_breached: bool) -> SystemState:
        if day_dd_breached or week_dd_breached:
            self._state = SystemState.HALTED
        return self._state


__all__ = ["SystemStateMachine"]
