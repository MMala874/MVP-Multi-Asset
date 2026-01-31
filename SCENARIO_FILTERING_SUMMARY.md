# Scenario Filtering Implementation Summary

## Overview
Implemented efficient scenario filtering in `BacktestOrchestrator.run()` to enable fast & serious two-stage tuning:
- **Stage 1**: Fast B-only evaluation on all grid candidates (1152 combos)
- **Stage 2**: Full A/B/C evaluation on top_k candidates only (e.g., 50 combos)

## Key Changes

### 1. BacktestOrchestrator.run() - Added Scenarios Parameter
**File**: `backtest/orchestrator.py`

**Change**: Added optional `scenarios` parameter to control which scenarios to evaluate
```python
def run(
    self,
    df_by_symbol: Dict[str, pd.DataFrame],
    config: Config,
    scenarios: list[str] | None = None,
) -> Tuple[pd.DataFrame, Dict[str, object]]:
```

**Behavior**:
- `scenarios=None` (default): Runs all scenarios A, B, C (backward compatible)
- `scenarios=["B"]`: Runs B scenario only
- `scenarios=["A", "B", "C"]`: Runs specified scenarios

**Implementation**:
```python
if scenarios is None:
    scenarios_to_run = [s.value for s in Scenario]
else:
    scenarios_to_run = scenarios

for scenario_id in scenarios_to_run:
    trades = _run_scenario(prepared, config, strategies, scenario_id)
    scenario_trades.append(trades)
```

### 2. Worker Functions - Pass Scenarios Parameter
**File**: `tuning/worker.py`

**Updated Functions**:

a) `run_worker_single_scenario()`: Pass single scenario to orchestrator
```python
trades, report = orchestrator.run(df_by_symbol, cfg_copy, scenarios=[scenario])
```

b) `run_worker_full_scenarios()`: Pass all three scenarios
```python
trades, report = orchestrator.run(df_by_symbol, cfg_copy, scenarios=["A", "B", "C"])
```

c) `run_worker()`: Pass None for backward compatibility
```python
trades, report = orchestrator.run(df_by_symbol, cfg_copy, scenarios=None)
```

### 3. Test Coverage - Scenario Filtering Tests
**File**: `tests/test_backtest.py`

**New Tests**:
1. `test_orchestrator_scenario_filtering()`: Verify B-only evaluation
2. `test_orchestrator_all_scenarios_default()`: Verify default runs all scenarios
3. `test_orchestrator_multiple_scenarios()`: Verify arbitrary scenario subsets

**Test Results**: All 3 new tests pass ✓

## Performance Impact

### Computational Efficiency
Traditional two-stage tuning (without scenario filtering):
- Stage 1: 1,152 combos × 3 scenarios = **3,456 runs**
- Stage 2: 50 combos × 3 scenarios = 150 runs
- **Total: 3,606 runs**

Fast & Serious tuning (with scenario filtering):
- Stage 1: 1,152 combos × 1 scenario = **1,152 runs** (3x faster!)
- Stage 2: 50 combos × 3 scenarios = 150 runs
- **Total: 1,302 runs (62% reduction)**

### Time Saved
- **2,304 fewer backtest runs** in Stage 1
- Assumes ~10 sec/run: **6.4 hours saved** on Stage 1 alone

## Backward Compatibility
✓ Fully backward compatible:
- Existing code calling `orchestrator.run(..., config)` works unchanged
- Default behavior (scenarios=None) runs all scenarios
- No breaking changes to existing APIs

## Integration with Two-Stage Tuning
The scenario filtering is now used in the multiprocessing tuning script:
- **Stage 1**: `run_worker_single_scenario(..., scenario="B")` for fast grid search
- **Stage 2**: `run_worker_full_scenarios(...)` for top_k validation

See `scripts/run_tuning_mp.py` for implementation details.

## Files Modified
1. `backtest/orchestrator.py` - Added scenarios parameter
2. `tuning/worker.py` - Pass scenarios to orchestrator.run()
3. `tests/test_backtest.py` - Added 3 scenario filtering tests + fixture

## Testing
**All tests pass**: 16/16 tests passing
- 8 existing tests (tuning infrastructure)
- 3 new scenario filtering tests
- 5 existing backtest tests

**Key Tests**:
- ✓ B-only scenario evaluation works
- ✓ All scenarios by default preserved
- ✓ Arbitrary scenario subsets work
- ✓ Two-stage tuning integration verified

## Usage Examples

### Example 1: B-only evaluation (Stage 1)
```python
orchestrator = BacktestOrchestrator()
trades, report = orchestrator.run(
    df_by_symbol, config, 
    scenarios=["B"]
)
# Only B scenario metrics in report
```

### Example 2: Full evaluation (Stage 2)
```python
trades, report = orchestrator.run(
    df_by_symbol, config, 
    scenarios=["A", "B", "C"]
)
# All three scenarios in metrics
```

### Example 3: Default (backward compatible)
```python
trades, report = orchestrator.run(
    df_by_symbol, config
)
# Same as scenarios=None, runs A/B/C
```

## Next Steps
1. Monitor Stage 1 performance improvements in tuning runs
2. Consider dynamic top_k selection based on stage 1 results
3. Add scenario filtering metrics/logging to progress reporting

## Commit Message
```
Implement scenario filtering: efficient B-only grid + A/B/C for top_k
- Add scenarios parameter to BacktestOrchestrator.run()
- Update worker functions to use scenario filtering
- Add 3 tests for scenario filtering behavior
- Enables 3x faster Stage 1 evaluation (1152 combos B-only)
- 62% reduction in total backtest runs for two-stage tuning
```
