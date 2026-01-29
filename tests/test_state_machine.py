from live.state_machine import SystemStateMachine


def test_state_transitions() -> None:
    machine = SystemStateMachine(max_execution_errors=2)
    assert machine.state.value == "RUNNING"

    machine.record_execution_error()
    assert machine.state.value == "DEGRADED"

    machine.record_execution_error()
    assert machine.state.value == "HALTED"

    machine = SystemStateMachine(max_execution_errors=3)
    machine.record_reconcile_mismatch()
    assert machine.state.value == "SAFE_MODE"

    machine.record_dd_flags(day_dd_breached=True, week_dd_breached=False)
    assert machine.state.value == "HALTED"
