# Scenario Filtering - Exact Code Changes

## File 1: backtest/orchestrator.py

### Before (lines 35-48)
```python
class BacktestOrchestrator:
    def run(self, df_by_symbol: Dict[str, pd.DataFrame], config: Config) -> Tuple[pd.DataFrame, Dict[str, object]]:
        _validate_bar_contract(config)
        strategies = _load_strategies(config)
        prepared = _prepare_features(df_by_symbol, strategies, config)

        scenario_trades: List[pd.DataFrame] = []
        for scenario in Scenario:
            trades = _run_scenario(prepared, config, strategies, scenario.value)
            scenario_trades.append(trades)

        trades_df = pd.concat(scenario_trades, ignore_index=True) if scenario_trades else _empty_trades()
        metrics = compute_metrics(trades_df)
        report = build_report(trades_df, metrics)
        return trades_df, report
```

### After (lines 40-72)
```python
class BacktestOrchestrator:
    def run(
        self,
        df_by_symbol: Dict[str, pd.DataFrame],
        config: Config,
        scenarios: list[str] | None = None,
    ) -> Tuple[pd.DataFrame, Dict[str, object]]:
        """Run backtest for given data and config.
        
        Args:
            df_by_symbol: OHLC data by symbol
            config: Backtest configuration
            scenarios: Optional list of scenario IDs to run (e.g., ["B"]).
                      If None, run all scenarios (A, B, C).
        """
        _validate_bar_contract(config)
        strategies = _load_strategies(config)
        prepared = _prepare_features(df_by_symbol, strategies, config)

        # Determine which scenarios to run
        if scenarios is None:
            scenarios_to_run = [s.value for s in Scenario]
        else:
            scenarios_to_run = scenarios

        scenario_trades: List[pd.DataFrame] = []
        for scenario_id in scenarios_to_run:
            trades = _run_scenario(prepared, config, strategies, scenario_id)
            scenario_trades.append(trades)

        trades_df = pd.concat(scenario_trades, ignore_index=True) if scenario_trades else _empty_trades()
        metrics = compute_metrics(trades_df)
        report = build_report(trades_df, metrics)
        return trades_df, report
```

**Key Changes**:
1. Added `scenarios: list[str] | None = None` parameter
2. Added docstring documenting the new parameter
3. Added conditional logic to determine which scenarios to run
4. Renamed loop variable from `scenario` to `scenario_id` for clarity

---

## File 2: tuning/worker.py

### run_worker_single_scenario (lines 46-47)

**Before**:
```python
    orchestrator = BacktestOrchestrator()
    trades, report = orchestrator.run(df_by_symbol, cfg_copy)
```

**After**:
```python
    orchestrator = BacktestOrchestrator()
    trades, report = orchestrator.run(df_by_symbol, cfg_copy, scenarios=[scenario])
```

### run_worker_full_scenarios (lines 112-113)

**Before**:
```python
    orchestrator = BacktestOrchestrator()
    trades, report = orchestrator.run(df_by_symbol, cfg_copy)
```

**After**:
```python
    orchestrator = BacktestOrchestrator()
    trades, report = orchestrator.run(df_by_symbol, cfg_copy, scenarios=["A", "B", "C"])
```

### run_worker (lines 177-178)

**Before**:
```python
    orchestrator = BacktestOrchestrator()
    trades, report = orchestrator.run(df_by_symbol, cfg_copy)
```

**After**:
```python
    orchestrator = BacktestOrchestrator()
    trades, report = orchestrator.run(df_by_symbol, cfg_copy, scenarios=None)
```

**Key Changes**:
- `run_worker_single_scenario`: Pass only the requested scenario
- `run_worker_full_scenarios`: Pass all three scenarios explicitly
- `run_worker`: Pass None for backward compatibility

---

## File 3: tests/test_backtest.py

### New Imports (line 2)
```python
import pytest
```

### New Fixture (lines 72-82)
```python
@pytest.fixture
def df_eurusd_1min_1000():
    """Create a 1000-bar EURUSD M1 fixture for testing."""
    import numpy as np
    n_bars = 1000
    np.random.seed(42)
    returns = np.random.randn(n_bars) * 0.001
    close = (1 + returns).cumprod()
    return pd.DataFrame({
        "open": close * (1 + np.random.randn(n_bars) * 0.0001),
        "high": close * (1 + np.abs(np.random.randn(n_bars) * 0.0003)),
        "low": close * (1 - np.abs(np.random.randn(n_bars) * 0.0003)),
        "close": close,
    })
```

### New Tests (lines 196-225)
```python
def test_orchestrator_scenario_filtering(df_eurusd_1min_1000):
    """Test that orchestrator can filter scenarios (e.g., run only B)."""
    config = _make_config()
    orchestrator = BacktestOrchestrator()
    
    # Run with scenarios=["B"] only
    trades, report = orchestrator.run({"EURUSD": df_eurusd_1min_1000}, config, scenarios=["B"])
    
    # Should have trades and report
    assert len(trades) > 0, "No trades generated for scenario B"
    assert "metrics" in report, "Report missing metrics"
    
    by_scenario = report["metrics"]["by_scenario"]
    
    # Only B scenario should be present
    assert "B" in by_scenario, "Scenario B missing from metrics"
    assert len(by_scenario) == 1, f"Expected only 1 scenario, got {len(by_scenario)}"
    
    # All trades should be from scenario B
    assert (trades["scenario"] == "B").all(), "Some trades are not from scenario B"


def test_orchestrator_all_scenarios_default(df_eurusd_1min_1000):
    """Test that orchestrator runs all scenarios by default (scenarios=None)."""
    config = _make_config()
    orchestrator = BacktestOrchestrator()
    
    # Run with scenarios=None (default)
    trades, report = orchestrator.run({"EURUSD": df_eurusd_1min_1000}, config, scenarios=None)
    
    # Should have all three scenarios
    by_scenario = report["metrics"]["by_scenario"]
    
    assert "A" in by_scenario, "Scenario A missing"
    assert "B" in by_scenario, "Scenario B missing"
    assert "C" in by_scenario, "Scenario C missing"
    assert len(by_scenario) == 3, f"Expected 3 scenarios, got {len(by_scenario)}"


def test_orchestrator_multiple_scenarios(df_eurusd_1min_1000):
    """Test that orchestrator can run specific scenario combinations."""
    config = _make_config()
    orchestrator = BacktestOrchestrator()
    
    # Run with scenarios=["A", "C"] (skip B)
    trades, report = orchestrator.run({"EURUSD": df_eurusd_1min_1000}, config, scenarios=["A", "C"])
    
    # Should have only A and C
    by_scenario = report["metrics"]["by_scenario"]
    
    assert "A" in by_scenario, "Scenario A missing"
    assert "C" in by_scenario, "Scenario C missing"
    assert "B" not in by_scenario, "Scenario B should not be present"
    assert len(by_scenario) == 2, f"Expected 2 scenarios, got {len(by_scenario)}"
```

**Key Changes**:
- Added pytest import
- Added `df_eurusd_1min_1000` fixture with 1000 bars of synthetic data
- Added 3 comprehensive tests for scenario filtering

---

## Summary of Changes

| File | Lines Changed | Type | Impact |
|------|---------------|------|--------|
| backtest/orchestrator.py | 22 | Addition | Core functionality |
| tuning/worker.py | 3 | Modification | Worker integration |
| tests/test_backtest.py | 60+ | Addition | Test coverage |
| **Total** | **85+** | **Net Addition** | **No breaking changes** |

## Backward Compatibility

✓ **Fully backward compatible**:
- Existing calls like `orchestrator.run(df, config)` still work
- Default behavior unchanged (runs all scenarios)
- No API signature breaking changes
- All existing tests continue to pass

## Integration Points

1. **BacktestOrchestrator**: Now supports scenario filtering ✓
2. **Worker functions**: All three workers integrated with scenario filtering ✓
3. **Two-stage tuning**: Stage 1 uses B-only, Stage 2 uses A/B/C ✓
4. **Tests**: 3 new tests verify scenario filtering behavior ✓
