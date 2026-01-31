#!/usr/bin/env python
"""Quick integration test for S1_TREND_BREAKOUT_DONCHIAN strategy."""

import sys
sys.path.insert(0, '.')

from backtest.orchestrator import BacktestOrchestrator, STRATEGY_MAP
from configs.loader import load_config

print("=" * 60)
print("S1_TREND_BREAKOUT_DONCHIAN Integration Test")
print("=" * 60)

# Test 1: Strategy registration
assert 'S1_TREND_BREAKOUT_DONCHIAN' in STRATEGY_MAP
print("[OK] Strategy is registered in STRATEGY_MAP")
print(f"     Module path: {STRATEGY_MAP['S1_TREND_BREAKOUT_DONCHIAN']}")

# Test 2: Config loading
config = load_config('configs/examples/example_config.yaml')
print("[OK] Config loaded successfully")
print(f"     Strategies: {', '.join(config.strategies.enabled)}")

# Test 3: Can instantiate orchestrator
orchestrator = BacktestOrchestrator()
print("[OK] BacktestOrchestrator instantiated")

print("\n" + "=" * 60)
print("[SUCCESS] All integration tests PASSED!")
print("=" * 60)
