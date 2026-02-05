#!/usr/bin/env python
"""
QUICK START: Running S7 HTF Trend / LTF Pullback Strategy

This script demonstrates how to run backtests with the S7 strategy.
"""

# ============================================================================
# EXAMPLE 1: Basic S7 backtest with all H4/H1 data
# ============================================================================
"""
Command:
python scripts/run_backtest.py \
  --config configs/examples/example_config.yaml \
  --eurusd data/eurusd_m15.csv \
  --eurusd_h1 data/eurusd_h1.csv \
  --eurusd_h4 data/eurusd_h4.csv \
  --out runs/s7_eurusd_full

Expected:
- S7 strategy loads successfully
- H4 features merged to M15 (49 valid trend_bias_h4 out of 50 bars)
- H1 features merged to M15 (atr_h1_pips in pips)
- Backtest runs end-to-end with S7 entry/exit signals
"""

# ============================================================================
# EXAMPLE 2: Multi-symbol S7 backtest
# ============================================================================
"""
Command:
python scripts/run_backtest.py \
  --config configs/examples/example_config.yaml \
  --eurusd data/eurusd_m15.csv \
  --eurusd_h1 data/eurusd_h1.csv \
  --eurusd_h4 data/eurusd_h4.csv \
  --gbpusd data/gbpusd_m15.csv \
  --gbpusd_h1 data/gbpusd_h1.csv \
  --gbpusd_h4 data/gbpusd_h4.csv \
  --out runs/s7_multi_symbol

Expected:
- Both EURUSD and GBPUSD backtested with S7
- Independent H4 bias direction per symbol
- report.json shows PnL for each symbol
"""

# ============================================================================
# EXAMPLE 3: ERROR CASE - Missing H4/H1 data
# ============================================================================
"""
Command (WILL FAIL):
python scripts/run_backtest.py \
  --config configs/examples/example_config.yaml \
  --eurusd data/eurusd_m15.csv \
  --out runs/s7_incomplete

Expected Error:
ValueError: Strategy S7_HTF_TREND_LTF_PULLBACK requires --eurusd_h4 and 
--eurusd_h1 to be provided

Fix:
Add --eurusd_h4 and --eurusd_h1 paths to command
"""

# ============================================================================
# S7 STRATEGY PARAMETERS (from config)
# ============================================================================
"""
H4 (Trend Bias):
  - ema_fast_h4: 50          (fast EMA period)
  - ema_slow_h4: 200         (slow EMA period)
  - adx_period_h4: 14        (ADX strength period)
  - adx_min_h4: 20.0         (minimum ADX for valid trend)

H1 (Stop Loss):
  - atr_period_h1: 14        (ATR period for stop sizing)
  - k_sl_h1: 1.5             (ATR multiplier for stop)
  - min_sl_points: 20        (minimum stop in pips)

M15 (Entry):
  - ema_period_pullback: 50  (pullback EMA period)
  - ema_period_trend: 200    (trend EMA period)
  - pullback_min: 0.3        (min pullback depth in ATR)
  - pullback_max: 1.2        (max pullback depth in ATR)

Exit:
  - Trailing stop via H1 Chandelier exit
  - No fixed take profit
"""

# ============================================================================
# KEY DESIGN PRINCIPLES
# ============================================================================
"""
1. MULTI-TIMEFRAME BIAS:
   - H4 EMA cross determines direction (+1, -1, or 0)
   - ADX >= adx_min_h4 confirms trend strength
   - Only trade when trend is confirmed

2. PULLBACK ENTRY:
   - M15 pullback forms between ema_pullback and ema_trend
   - Depth validated: 0.3 to 1.2 ATR range
   - Entry on close cross of pullback EMA in trend direction

3. STOP LOSS (PIPS):
   - Sized from H1 ATR: max(k_sl_h1 * atr_h1_pips, min_sl_points)
   - atr_h1_pips = H1 ATR / pip_size (e.g., EURUSD: ATR 0.0015 / 0.0001 = 15 pips)
   - Always in correct pip units

4. TRAILING EXIT:
   - H1 Chandelier exit (high-based for longs, low-based for shorts)
   - No fixed take profit (trailing only)

5. NO LOOKAHEAD:
   - H4/H1 features shifted(1) before merge → uses closed bars only
   - Merge via backward merge_asof → no future data visible
   - Double validation in tests
"""

# ============================================================================
# EXPECTED OUTPUT
# ============================================================================
"""
logs/backtest_YYYY-MM-DD.log:
  - Data loading messages for M15/H1/H4
  - H4 merge summary: trend_bias_h4 valid count
  - H1 merge summary: atr_h1_pips valid count
  - Strategy instantiation for S7
  - Entry/exit signals with tags

runs/report.json:
  - Total return %
  - Max drawdown %
  - Sharpe ratio
  - Win rate
  - Per-trade statistics

runs/trades.csv:
  - entry_time, entry_price, exit_time, exit_price, pnl
  - signal_tags showing strategy parameters (bias_h4, adx_h4, atr_h1_pips)
"""

# ============================================================================
# DEBUGGING
# ============================================================================
"""
To inspect S7 signals without running full backtest:

python -c "
from scripts.run_backtest import _load_symbols
from configs.loader import load_config
import argparse

cfg = load_config('configs/examples/example_config.yaml')
args = argparse.Namespace(
    eurusd='data/eurusd_m15.csv',
    eurusd_h1='data/eurusd_h1.csv',
    eurusd_h4='data/eurusd_h4.csv',
    gbpusd=None, gbpusd_h1=None, gbpusd_h4=None,
    usdjpy=None, usdjpy_h1=None, usdjpy_h4=None,
)
symbols = _load_symbols(args, cfg)
print('M15 columns:', symbols['EURUSD'].columns.tolist())
print('Trend bias H4 valid:', symbols['EURUSD']['trend_bias_h4'].notna().sum())
print('ATR H1 pips valid:', symbols['EURUSD']['atr_h1_pips'].notna().sum())
"
"""

# ============================================================================
# COMMON ISSUES
# ============================================================================
"""
Issue: ValueError: "requires --eurusd_h4 and --eurusd_h1"
Fix: Add both --eurusd_h1 and --eurusd_h4 flags

Issue: trend_bias_h4 all NaN
Fix: Check that H4 data time range overlaps with M15
     Check that H4 has >= 250 bars (for 200-bar EMA warmup)

Issue: atr_h1_pips values too large or small
Fix: Verify pip_size lookup in data/fx.py PIP_SIZES
     EURUSD: 0.0001, GBPUSD: 0.0001, USDJPY: 0.01

Issue: No S7 signals generated
Fix: Check H4 ADX >= adx_min_h4 (default 20.0)
     Check pullback depth within 0.3-1.2 ATR range
     Check ema_slope_m15 aligns with bias direction
"""

print(__doc__)
