from backtest.orchestrator import BacktestOrchestrator
from risk.allocator import RiskAllocator


def test_imports_smoke() -> None:
    assert BacktestOrchestrator is not None
    assert RiskAllocator is not None
