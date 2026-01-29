from __future__ import annotations

from desk_types import SystemState


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
