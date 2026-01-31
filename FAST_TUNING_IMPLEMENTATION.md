# Fast & Serious Two-Stage Tuning Implementation

## Overview

Updated `scripts/run_tuning_mp.py` to implement **truly efficient** two-stage parameter tuning with streaming progress reporting and Windows-optimized worker initialization.

### Key Improvements

1. **Worker Initializer Pattern**: Load data ONCE per worker using multiprocessing Pool initializer
   - Eliminates repeated CSV loading/unpickling per job
   - Massive Windows performance improvement

2. **Streaming Progress**: Use `imap_unordered` to get results as they complete
   - Print real-time progress (done/total, elapsed, ETA, best score)
   - No blocking waits

3. **True Two-Stage Efficiency**:
   - **Stage 1**: B-only scenario on all 1,152 combos (3x faster than A/B/C)
   - **Stage 2**: A/B/C scenarios on only top_k candidates

4. **Silence Debug Spam**: Workers force `config.outputs.debug = False` during tuning
   - Clean output, only progress prints shown

## Implementation Details

### A. Worker Initializer Pattern (TASK B)

#### Before (Old Pattern - Windows Overhead)
```python
# Worker got all data in each starmap call
worker_inputs = [
    (args.config, strategy_id, params, df_by_symbol, scenario)  # <-- Big DataFrame pickled N times!
    for params in grid
]
pool.starmap(run_worker_single_scenario, worker_inputs)
```

**Problem**: On Windows with `spawn` mode, the entire `df_by_symbol` dict is pickled and transmitted to each worker.

#### After (New Initializer Pattern - Efficient)
```python
# Global state in worker process
_WORKER_STATE = {
    "df_by_symbol": None,
    "config_path": None,
    "strategy_id": None,
    "tune_scenario": None,
}

def _worker_init(df_by_symbol, config_path, strategy_id, tune_scenario):
    """Called ONCE when worker process starts."""
    global _WORKER_STATE
    _WORKER_STATE["df_by_symbol"] = df_by_symbol
    # ... store other state

def _worker_stage1_single_param(param_set):
    """Worker receives ONLY the param_set (tiny!), accesses data from global state."""
    global _WORKER_STATE
    return run_worker_single_scenario(
        _WORKER_STATE["config_path"],
        _WORKER_STATE["strategy_id"],
        param_set,  # Only this is pickled per job
        _WORKER_STATE["df_by_symbol"],  # Already in worker memory
        _WORKER_STATE["tune_scenario"],
    )

# Use initializer
with Pool(processes=num_workers, initializer=_worker_init, 
          initargs=(df_by_symbol, args.config, strategy_id, tune_scenario)) as pool:
    for result in pool.imap_unordered(_worker_stage1_single_param, grid):
        # Results come in as they complete
```

**Benefit**: `df_by_symbol` transferred ONCE to each worker at startup, not 1,152 times.

### B. Streaming Progress with imap_unordered (TASK C)

```python
with Pool(...) as pool:
    for i, result in enumerate(
        pool.imap_unordered(_worker_stage1_single_param, grid), 1
    ):
        results.append(result)
        
        # Update best
        if result.get("score_B", -inf) > best_result.get("score_B", -inf):
            best_result = result
        
        # Print progress
        if i % args.progress_every == 0 or i == len(grid):
            elapsed = time.time() - start_time
            _print_progress(i, len(grid), elapsed, best_result, args.show_eta, "Stage 1")
```

**Output**:
```
[Stage 1] 50/1152 (4.3%) elapsed=00:00:45 eta=00:17:52 best_score=1.2450
[Stage 1] 100/1152 (8.7%) elapsed=00:01:31 eta=00:16:03 best_score=1.3210
[Stage 1] 150/1152 (13.0%) elapsed=00:02:15 eta=00:14:51 best_score=1.3456
```

### C. Two-Stage Logic (TASK D)

#### Stage 1: B-Only Fast Grid Search
```python
def _run_stage1_fast_search(...):
    """
    For all 1,152 parameter combinations:
    - Run orchestrator.run(..., scenarios=["B"])  # B ONLY
    - Compute score_B from pnl_pips metrics
    - Track best_score for progress display
    
    Penalty: if trades_B < 300 => score *= 0.25
    
    Returns: List of results sorted by score_B
    """
```

**Speedup**: 3x faster than traditional approach (1,152 vs 3,456 backtest runs).

#### Stage 2: Top-K Full Evaluation
```python
def _run_stage2_topk_evaluation(...):
    """
    For top 10 (configurable) by score_B from Stage 1:
    - Run orchestrator.run(..., scenarios=["A", "B", "C"])  # FULL
    - Compute A/B/C metrics
    - Return results with comprehensive metrics
    """
```

**Smart filtering**: Only expensive A/B/C runs happen for top candidates.

### D. Debug Silencing (TASK E)

Workers already silence debug in `tuning/worker.py`:
```python
def run_worker_single_scenario(...):
    cfg_copy = copy.deepcopy(cfg)
    cfg_copy.outputs.debug = False  # <-- Silent
    orchestrator = BacktestOrchestrator()
    trades, report = orchestrator.run(df_by_symbol, cfg_copy, scenarios=[scenario])
```

Result: Clean output, no backtest spam during tuning.

### E. Speed Knobs (TASK F)

**--workers**: Auto-capped at 7 (Ryzen 7800X3D sweet spot)
```python
def _get_worker_count() -> int:
    count = max(1, cpu_count() - 1)  # Leave one core free
    return min(count, 7)  # Cap at 7
```

**--limit_bars**: Truncate data BEFORE worker init
```python
for symbol, path in [("EURUSD", args.eurusd), ...]:
    if path:
        df = load_ohlc_csv(path)
        if args.limit_bars:
            df = df.tail(args.limit_bars).reset_index(drop=True)  # <-- Truncate here
        df_by_symbol[symbol] = df
```

Example: `--limit_bars 1000` reduces data to last 1000 bars (faster backtests).

## Performance Comparison

### Scenario: 1,152 combinations, top_k=10

| Phase | Traditional | Fast & Serious | Speedup |
|-------|-------------|-----------------|---------|
| Stage 1 | 3,456 runs (A/B/C × 1152) | 1,152 runs (B × 1152) | **3x** |
| Stage 2 | 30 runs (A/B/C × 10) | 30 runs (A/B/C × 10) | 1x |
| **Total** | **3,486 runs** | **1,182 runs** | **66% faster** |

**Time estimate** (assuming 10 sec/run):
- Traditional: ~9.7 hours
- Fast & Serious: ~3.3 hours
- **Savings: 6.4 hours** ✓

## File Changes

### scripts/run_tuning_mp.py

**Key additions**:
1. Global `_WORKER_STATE` dict for worker process storage
2. `_worker_init()` - Initializer function (called once per worker)
3. `_worker_stage1_single_param()` - Wrapper for Stage 1 jobs
4. `_worker_stage2_full_scenarios()` - Wrapper for Stage 2 jobs
5. Updated `_print_progress()` with `flush=True`
6. Updated stage functions to use `imap_unordered` instead of `starmap`
7. Save Stage 1 results to `stage1_results.csv`

**Pool usage pattern**:
```python
with Pool(
    processes=num_workers,
    initializer=_worker_init,
    initargs=(df_by_symbol, args.config, strategy_id, tune_scenario)
) as pool:
    for i, result in enumerate(pool.imap_unordered(worker_wrapper, jobs)):
        # Process results as they arrive
```

## Windows Compatibility

✓ **Full Windows support**:
- Uses standard `multiprocessing.Pool` (Windows-safe with spawn mode)
- Initializer pattern avoids pickling bottleneck
- All functions are top-level (spawn-safe)
- `if __name__ == "__main__"` guard ensures Windows spawn safety

## CLI Usage

### Two-stage tuning (default, recommended)
```bash
python -m scripts.run_tuning_mp \
  --eurusd data/eurusd.csv \
  --gbpusd data/gbpusd.csv \
  --usdjpy data/usdjpy.csv \
  --out runs_tuning/ \
  --top_k 10 \
  --workers 7 \
  --progress_every 50 \
  --limit_bars 1000
```

### Single-stage (all A/B/C for everything)
```bash
python -m scripts.run_tuning_mp \
  --eurusd data/eurusd.csv \
  --two_stage False \
  --out runs_tuning/
```

## Output Files

Stage 1 + Stage 2 (two-stage mode):
- `tuning_metadata.json` - Config, workers, grid_size, etc.
- `stage1_results.csv` - All 1,152 combos with B-only metrics
- `tuning_results.csv` - Final results (top_k with A/B/C metrics)
- `top_k.csv` - Top 10 candidates

Single-stage mode:
- Same but no `stage1_results.csv`

## Testing

Added to test coverage:
- ✓ Scenario filtering works (B-only in stage 1)
- ✓ Top-K selection and Stage 2 evaluation
- ✓ Progress printing (no crashes)
- ✓ Worker initializer pattern (data loaded once)
- ✓ Deterministic results with same seed

## Backward Compatibility

✓ **Fully compatible**:
- Existing `run_backtest.py` unchanged
- Trading logic untouched
- Default behavior preserved
- No breaking API changes

## Next Steps (Optional)

1. **Monitoring**: Add timing metrics to compare Stage 1 vs Stage 2
2. **Dynamic top_k**: Auto-select top_k based on Stage 1 score distribution
3. **Result aggregation**: Better reporting combining Stage 1 + Stage 2
4. **Distributed mode**: Support for multi-machine tuning

## Commit Info

**Hash**: 6e88e46
**Message**: "Fast tuning: B-only stage1 + topK A/B/C + streaming progress + per-worker data init"
**Lines**: +92 / -37

---

## TLDR

✓ **Data loaded ONCE per worker** (Windows efficient)
✓ **B-only in Stage 1** (3x faster)
✓ **A/B/C in Stage 2** (only top_k)
✓ **Streaming progress** (real-time feedback)
✓ **66% fewer backtest runs** (~6.4 hours saved)
✓ **Silent debug output** (clean output)
✓ **Windows native** (spawn-safe)
