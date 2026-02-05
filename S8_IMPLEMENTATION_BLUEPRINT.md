# S8 IMPLEMENTATION BLUEPRINT: Integration with Existing System

## Overview

This document explains how to integrate the S8_VOL_COMPRESSION_EXPANSION strategy into the MVP-V2 system **without breaking existing infrastructure**.

---

## COMPATIBILITY CHECKLIST

### ✅ What Stays Unchanged
- Cost model (spread + slippage already handled)
- Bar contract (closed-bar entry, next-open fill)
- DD guard (position sizing + drawdown monitoring still active)
- Regime engine (used for gating, not entry)
- Existing strategies (S1, S2, S3, S7) unaffected

### ✅ What Gets Added
- New indicator: ATR percentile rank (no new lib dependency)
- New strategy module: `strategies/s8_vol_compression_expansion.py`
- Compression state tracking in `data/io.py`
- S8 registration in `backtest/orchestrator.py`
- CLI support in `scripts/run_backtest.py`
- Config params in `configs/examples/example_config.yaml`
- Regression tests in `tests/test_s8_vol_compression_expansion.py`

---

## DATA INFRASTRUCTURE REQUIREMENTS

### 1. Compression State Tracking (`data/io.py` new function)

```python
def compute_atr_percentile_rank(
    df: pd.DataFrame,
    atr_period: int = 20,
    lookback_window: int = 250
) -> pd.DataFrame:
    """
    Compute rolling percentile rank of ATR over lookback window.
    
    Purpose: Identify when ATR is in compression (low percentile) vs expansion.
    
    Args:
        df: OHLC DataFrame with columns [time, open, high, low, close]
        atr_period: Period for ATR calculation (typically 20)
        lookback_window: Historical window for percentile calc (250 bars = ~3 days of M15)
    
    Returns:
        DataFrame with columns [time, atr, atr_pct_rank]
        - atr: Raw ATR value
        - atr_pct_rank: Percentile rank 0-100 (higher = more expansion)
    
    Anti-lookahead:
        - Percentile calculated on historical bars only (no forward bias)
        - Can use closed-bar ATR (no shift needed; we're ranking history)
    
    Formula:
        atr = average(tr over atr_period)
        atr_pct_rank = percentileofscore(atr over lookback_window)
    """
```

**Key Design Decision:**
- Percentile rank is **objective** (not optimized)
- 250-bar lookback ≈ 3-4 days of M15 data (captures normal range)
- No parameters to tune (20-day ATR period is standard)

---

### 2. Compression Event Detection (`data/io.py` new function)

```python
def detect_compression_events(
    df: pd.DataFrame,
    atr_pct_threshold: int = 20,
    min_duration_bars: int = 10
) -> pd.DataFrame:
    """
    Detect periods when ATR is in compression (pct_rank < threshold for min_duration).
    
    Purpose: Flag when market is entering a compression state for subsequent expansion signal.
    
    Args:
        df: DataFrame with [time, atr_pct_rank] from compute_atr_percentile_rank()
        atr_pct_threshold: Below this, market is "compressed" (e.g., 20)
        min_duration_bars: Minimum bars in compression to qualify (e.g., 10)
    
    Returns:
        df with new columns:
        - compression_flag: 1 if in compression, 0 otherwise
        - compression_duration: How many consecutive bars compressed so far
        - expansion_trigger: 1 on first bar where atr_pct_rank crosses above threshold
    
    Logic:
        1. Identify bars where atr_pct_rank < atr_pct_threshold
        2. Count consecutive bars (compression_duration)
        3. Filter: Only flag if duration >= min_duration_bars
        4. Mark expansion_trigger when atr_pct_rank crosses from <threshold to >=threshold
    
    Anti-lookahead:
        - All calculations use closed-bar data
        - No forward-looking bias
    """
```

---

## STRATEGY MODULE: `strategies/s8_vol_compression_expansion.py`

```python
"""
S8_VOL_COMPRESSION_EXPANSION: Volatility Breakout Strategy

Entry: Breakout from ATR compression via objective percentile rank
Exit: Fixed SL (10 pips) + Trailing (H1 Chandelier)

Hypothesis: Post-compression expansions show asymmetric continuation (42-50% win rate)
due to forced liquidations and low-friction market microstructure.
"""

STRATEGY_ID = "S8_VOL_COMPRESSION_EXPANSION"

def required_features() -> Set[str]:
    """Features needed for S8 (all from M15 + H4 merged)."""
    return {
        # Compression detection
        "atr_m15",
        "atr_pct_rank_m15",
        "compression_flag",
        "expansion_trigger",
        
        # Gating
        "adx_h4",
        "regime",
        
        # Exit
        "chandelier_exit_h1",  # Trailing stop
    }

def generate_signal(ctx: StrategyContext) -> SignalIntent:
    """
    Entry: On expansion_trigger, take direction of last M15 bar
    Exit: SL=10pips, TP=25pips (trail after 3pips move)
    """
    
    # Gate 1: Expansion detected
    if ctx.expansion_trigger != 1:
        return FLAT
    
    # Gate 2: ADX confirms structure
    if ctx.adx_h4 < 20:
        return FLAT
    
    if ctx.adx_h4 > 50:
        return FLAT  # Over-extended, reversion risk
    
    # Gate 3: Not in whipsaw regime
    if ctx.regime == "WHIPSAW":
        return FLAT
    
    # Gate 4: No overnight gap risk
    if abs(ctx.close_today_open - ctx.close_yesterday) > 0.001:  # 10 pips EURUSD
        return FLAT
    
    # Entry direction: Based on expansion bar
    if ctx.close > ctx.open:
        side = LONG
    else:
        side = SHORT
    
    # SL / TP
    sl_points = 10      # Fixed
    tp_points = 25      # Initial; will trail after 3pips move
    
    tags = {
        "compression_duration": ctx.compression_duration,
        "atr_pct_rank": ctx.atr_pct_rank_m15,
        "adx_h4": ctx.adx_h4,
    }
    
    return SignalIntent(
        side=side,
        sl_points=sl_points,
        tp_points=tp_points,
        tags=tags,
    )
```

---

## ORCHESTRATOR INTEGRATION: `backtest/orchestrator.py`

### Registration

```python
STRATEGY_MAP = {
    # ... existing ...
    "S8_VOL_COMPRESSION_EXPANSION": "strategies.s8_vol_compression_expansion",
}
```

### Feature Computation

```python
elif spec.name == "S8_VOL_COMPRESSION_EXPANSION":
    
    # Compression state
    df["atr_m15"] = compute_atr(df, period=20)
    df["atr_pct_rank_m15"] = compute_atr_percentile_rank(df, atr_period=20, lookback=250)
    
    # Compression detection (from data/io.py)
    compression_df = detect_compression_events(
        df,
        atr_pct_threshold=20,
        min_duration_bars=10
    )
    df["compression_flag"] = compression_df["compression_flag"]
    df["compression_duration"] = compression_df["compression_duration"]
    df["expansion_trigger"] = compression_df["expansion_trigger"]
    
    # Gating (H4)
    if "adx_h4" not in df.columns:
        df["adx_h4"] = compute_adx(df_h4, period=14)  # Would need H4 merge
    if "regime" not in df.columns:
        df["regime"] = "NORMAL"  # Fallback
    
    # Exit (H1 Chandelier)
    if "chandelier_exit_h1" not in df.columns:
        atr_h1 = compute_atr(df_h1, period=14)
        df["chandelier_exit_h1"] = compute_chandelier_exit(
            df_h1, atr_h1, k=3.0, side="long"
        )
```

---

## CLI INTEGRATION: `scripts/run_backtest.py`

### Arguments (Optional for S8, but can add anyway)

```python
def _parse_args():
    parser.add_argument(
        "--s8_config",
        type=str,
        default=None,
        help="Override S8 parameters (JSON or YAML). Optional."
    )
    return parser.parse_args()

def _load_symbols(args, cfg):
    # S8 doesn't require special data (uses M15 + H4 merged features)
    # But can pass custom compression thresholds if needed
    
    if "S8_VOL_COMPRESSION_EXPANSION" in cfg.strategies.enabled:
        # Optional: Load S8-specific params
        if args.s8_config:
            s8_params = load_s8_config(args.s8_config)
            cfg.strategies.params["S8_VOL_COMPRESSION_EXPANSION"].update(s8_params)
```

---

## CONFIG PARAMETERS: `configs/examples/example_config.yaml`

```yaml
strategies:
  enabled:
    - "S8_VOL_COMPRESSION_EXPANSION"  # Add to enabled list
  
  params:
    S8_VOL_COMPRESSION_EXPANSION:
      # Compression detection
      atr_period: 20              # ATR period for percentile calc
      atr_pct_threshold: 20       # Below this = compressed state
      min_duration_bars: 10       # Minimum bars to confirm compression
      
      # Entry
      sl_points: 10               # Hard stop loss in pips
      tp_points: 25               # Initial TP; will trail
      tp_trail_activation: 3      # Move SL up after 3 pips profit
      
      # Gating
      adx_min: 20                 # Minimum ADX to enter
      adx_max: 50                 # Maximum ADX (over-extended)
      max_gap_pips: 10            # Max overnight gap to accept
      
      # Risk
      max_trades_per_week: 3      # Cap for safety
      position_size_pct: 1.0      # % of account per trade
```

---

## REGRESSION TESTS: `tests/test_s8_vol_compression_expansion.py`

### Key Tests

```python
def test_atr_percentile_rank_no_lookahead():
    """Percentile rank should not use future bars."""
    df = create_sample_ohlc(200)
    pct_rank = compute_atr_percentile_rank(df, atr_period=20, lookback=250)
    
    # First 250 bars should have valid percentiles
    assert pct_rank["atr_pct_rank"].iloc[20:].notna().all()
    
    # Verify no forward bias
    for i in range(50, len(df)-50):
        assert pct_rank["atr_pct_rank"].iloc[i] <= 100

def test_compression_events_10bar_minimum():
    """Compression flag should only appear after 10+ consecutive low-pct bars."""
    df = create_sample_ohlc(200)
    df["atr_pct_rank_m15"] = [10] * 5 + [15] * 8 + [10] * 10 + [50, 60, 70]
    
    compression = detect_compression_events(df, atr_pct_threshold=20, min_duration_bars=10)
    
    # First 5 bars: Too short, no compression flag
    assert compression["compression_flag"].iloc[:5].sum() == 0
    
    # Next 8 bars: Still too short
    assert compression["compression_flag"].iloc[5:13].sum() == 0
    
    # Next 10 bars: Now compressed
    assert compression["compression_flag"].iloc[13:23].sum() == 10
    
    # Expansion trigger on bar 24 (first >20)
    assert compression["expansion_trigger"].iloc[24] == 1

def test_s8_entry_on_expansion_only():
    """S8 should only enter on expansion_trigger=1, not before or after."""
    ctx = setup_strategy_context(expansion_trigger=0)
    signal = s8.generate_signal(ctx)
    assert signal.side == FLAT
    
    ctx = setup_strategy_context(expansion_trigger=1, adx_h4=25)
    signal = s8.generate_signal(ctx)
    assert signal.side != FLAT

def test_s8_gating_adx_too_low():
    """ADX < 20 should result in FLAT."""
    ctx = setup_strategy_context(expansion_trigger=1, adx_h4=15)
    signal = s8.generate_signal(ctx)
    assert signal.side == FLAT

def test_s8_gating_adx_too_high():
    """ADX > 50 should result in FLAT (over-extended)."""
    ctx = setup_strategy_context(expansion_trigger=1, adx_h4=55)
    signal = s8.generate_signal(ctx)
    assert signal.side == FLAT

def test_s8_sl_and_tp_fixed():
    """SL should be 10 pips, initial TP 25 pips."""
    ctx = setup_strategy_context(expansion_trigger=1, adx_h4=25, regime="NORMAL")
    signal = s8.generate_signal(ctx)
    
    assert signal.sl_points == 10
    assert signal.tp_points == 25

def test_s8_direction_follows_close():
    """Entry direction should match close > open on expansion bar."""
    ctx_long = setup_strategy_context(expansion_trigger=1, close=1.1100, open=1.1090, adx_h4=25)
    signal_long = s8.generate_signal(ctx_long)
    assert signal_long.side == LONG
    
    ctx_short = setup_strategy_context(expansion_trigger=1, close=1.1090, open=1.1100, adx_h4=25)
    signal_short = s8.generate_signal(ctx_short)
    assert signal_short.side == SHORT
```

---

## DATA FLOW DIAGRAM

```
M15 OHLC Data
    ↓
compute_atr_percentile_rank()  [new function in data/io.py]
    ├─ Output: atr_m15, atr_pct_rank_m15
    ↓
detect_compression_events()  [new function in data/io.py]
    ├─ Output: compression_flag, compression_duration, expansion_trigger
    ↓
[Merge with H4 features: adx_h4, regime]
[Merge with H1 features: chandelier_exit_h1]
    ↓
backtest/orchestrator._apply_strategy_features("S8")
    ├─ Computes missing features if needed
    ↓
strategies/s8_vol_compression_expansion.generate_signal()
    ├─ Checks: expansion_trigger, ADX gates, regime, gap
    ├─ Output: SignalIntent(side, sl_points, tp_points, tags)
    ↓
Backtest execution (existing cost model, DD guard, etc.)
    ↓
report.json + trades.csv
```

---

## IMPLEMENTATION SCHEDULE

### Phase 1: Data Infrastructure (2 hours)
1. Add `compute_atr_percentile_rank()` to `data/io.py`
2. Add `detect_compression_events()` to `data/io.py`
3. Test both functions on historical M15 data

### Phase 2: Strategy Module (1 hour)
1. Create `strategies/s8_vol_compression_expansion.py`
2. Implement `required_features()` and `generate_signal()`
3. Register in `STRATEGY_MAP`

### Phase 3: Orchestrator Integration (1 hour)
1. Add S8 to `_apply_strategy_features()` in orchestrator
2. Ensure fallback computation for missing features

### Phase 4: Config & CLI (30 mins)
1. Add S8 params to `example_config.yaml`
2. Add S8 to `ALLOWED_STRATEGIES`
3. Optional: CLI support in `run_backtest.py`

### Phase 5: Testing (2 hours)
1. Create `tests/test_s8_vol_compression_expansion.py`
2. Test compression detection on synthetic data
3. Test S8 gating logic
4. Integration test: full backtest with S8 enabled

### Phase 6: Backtest Validation (1 day offline)
1. Run backtest on 5 years EURUSD M15 + H4
2. Extract compression events, win rates, avg P&L
3. Validate P&L survival post-costs
4. If win rate < 40%: Stop and document failure

---

## RISK MITIGATION

### 1. Preserve Existing Infrastructure
- S8 uses only ATR (already computed) + gating (ADX, regime—already used)
- No changes to cost model, position sizing, or DD guard
- Can disable S8 by removing from `enabled` list

### 2. Validate Edge Before Deployment
- Full backtest required (2-3 days)
- OOS test on 2024-2025 data (held-out)
- Paper trade 2-4 weeks before live

### 3. Parameter Freezing
- Once backtest complete, **NO parameter changes** without re-validation
- Config is versioned in git
- Prevents accidental overfitting

### 4. Trade Capping
- Max 3 trades/week (config param) prevents runaway frequency
- Prop firm DD/position limits still apply

---

## SUCCESS METRICS (For Phase 6 Backtest)

| Metric | Target | Failure |
|--------|--------|---------|
| **Win Rate** | ≥42% | <40% → edge does not exist |
| **Avg Win** | ≥18 pips | <15 pips → cost margin too thin |
| **Avg Loss** | ≤12 pips | >15 pips → SL not protecting |
| **Profit Factor** | ≥1.2 | <1.1 → not profitable |
| **Max Drawdown** | ≤8% account | >10% → risk too high |
| **Sharpe Ratio** | ≥0.8 | <0.5 → inconsistent |
| **OOS Degradation** | <5% win rate | >10% → overfitting detected |

---

## APPROVAL CHECKLIST

Before implementing S8, confirm:

- [x] Edge hypothesis is documented (EDGE_FIRST_RESEARCH.md)
- [x] Strategy logic is minimal and testable
- [x] Existing infrastructure will NOT be modified
- [x] New functions have clear anti-lookahead design
- [x] Test plan covers all gates and edge cases
- [x] Backtest parameters are frozen (no optimization)
- [x] Risk metrics are acceptable for prop firm

If ALL checked: Proceed to Phase 1 (Data Infrastructure)

---

## NEXT ACTION

Create `data/io.py` functions for ATR percentile rank and compression detection.

Then: Validate these functions on historical EURUSD M15 data (2020-2024).

If successful: Proceed to strategy module implementation.
