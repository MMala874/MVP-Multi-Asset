TICK-LEVEL EDGE DISCOVERY SCANNER
==================================

OVERVIEW
--------
tick_edge_scan.py performs rigorous statistical edge discovery on MT5 tick data.

It detects volatility compression events and measures post-event return distribution shifts.
Decision: GO/NO-GO based on effect size consistency across years (not single-year anomalies).


HOW TO USE
----------

1. EXPORT MT5 TICK DATA
   -----
   • Open MT5 terminal
   • Tools → History Center
   • Download EURUSD tick data (M1 or lower, full tick history)
   • Export as CSV via right-click on symbol
   • Ensure columns: time (or datetime), bid, ask
   • Save to: data/EURUSD_ticks.csv

2. RUN SCANNER
   -----------
   Basic (synthetic data for testing):
     python scripts/tick_edge_scan.py --verbose

   With real MT5 data:
     python scripts/tick_edge_scan.py \
       --tick_file data/EURUSD_ticks.csv \
       --output_dir outputs \
       --verbose

   Custom thresholds:
     python scripts/tick_edge_scan.py \
       --tick_file data/EURUSD_ticks.csv \
       --tick_count_percentile 10 \      # Lower = stricter compression
       --range_percentile 10 \           # Lower = smaller tick range
       --spread_percentile 20 \          # Lower = tighter spreads
       --compression_duration_min 10 \   # Min duration in minutes
       --lookback_window_days 2 \        # Historical percentile window
       --verbose

3. INTERPRET RESULTS
   -----------------
   Output files:
     • outputs/events.csv - one row per compression event
     • outputs/summary.json - effect sizes + stability

   Decision logic:
     DECISION: GO
       → Effect size ratio > 1.05 in >= 60% of years
       → Edge is consistent, not single-year anomaly
       → Proceed to live backtesting

     DECISION: NO-GO
       → Effect size < 1.05 OR < 60% year consistency
       → Edge is weak or unstable
       → Stop, revisit hypothesis


PARAMETERS EXPLAINED
--------------------

--tick_count_percentile (default 10)
  Events where tick_count is below Nth percentile of historical distribution
  Lower = stricter (fewer, more extreme events)
  Typical: 10-20

--range_percentile (default 10)
  Events where micro_range (max_bid - min_bid) is below Nth percentile
  Lower = stricter compression
  Typical: 5-15

--spread_percentile (default 20)
  Events where spread_std (variability of bid-ask spread) is below Nth percentile
  Lower = stricter (tighter, more stable spreads)
  Typical: 15-30

--compression_duration_min (default 10)
  Minimum duration an event must persist (in 1-minute bars)
  Higher = longer, more rare events
  Typical: 5-20

--lookback_window_days (default 2)
  Historical window for computing percentile (2 days = ~3000 bars)
  Longer = more stable baseline, less sensitivity to recent regime
  Typical: 1-5

--bar_period_sec (default 60)
  Candle period in seconds (60 = 1-minute bars, 300 = 5-minute)
  Keep at 60 for tick-level detail


OUTPUTS EXPLAINED
-----------------

events.csv
  One row per detected compression event with:
    • event_start_time, event_end_time, event_duration_min
    • entry_time, entry_bid (where strategy would enter)
    • forward_vol_5m, forward_vol_15m, forward_vol_30m (realized volatility post-event)
    • forward_range_* (price range post-event)
    • forward_return_mean/std/p95_* (return statistics)
    • year (for per-year analysis)

summary.json
  • metadata: data range, n_ticks, n_bars, n_events
  • parameters: all input thresholds
  • baseline: unconditional metrics (no compression condition)
  • effect_sizes: ratio of post-event metrics to baseline
  • stability_per_year: year-by-year breakdown
  • decision: GO/NO-GO + consistency %


INTERPRETATION GUIDE
--------------------

vol_ratio_5m = 1.15
  → Forward volatility 5 minutes after event is 15% higher than baseline
  → Effect exists, but modest

vol_ratio_5m = 0.85
  → Forward volatility 5 minutes after event is 15% lower than baseline
  → Could indicate compression → mean-reversion (edge)

vol_5m_consistency = 80%
  → Effect observed in 80% of years
  → Robust, not single-year lucky

vol_5m_consistency = 40%
  → Effect observed in 40% of years
  → Unreliable, likely random


EXAMPLE WORKFLOW
----------------

1. Export EURUSD ticks from MT5 (2023-2025) to data/EURUSD_ticks.csv

2. Initial scan with defaults:
   python scripts/tick_edge_scan.py --tick_file data/EURUSD_ticks.csv --verbose
   
   Output: NO-GO (not enough events or effect too small)

3. Relax thresholds to find more events:
   python scripts/tick_edge_scan.py \
     --tick_file data/EURUSD_ticks.csv \
     --tick_count_percentile 20 \
     --range_percentile 20 \
     --spread_percentile 30 \
     --verbose
   
   Output: GO (vol_ratio = 1.12, consistency = 75%)

4. If GO: proceed to live backtesting with frozen parameters
   - Use same thresholds as step 3
   - Build operational entry/exit logic (separate)
   - Test on full data + OOS years


ANTI-LOOKAHEAD VALIDATION
--------------------------

All calculations use BACKWARD-ONLY data:
  ✓ Percentile ranks computed from historical bars (no future info)
  ✓ Compression detection uses closed bars only
  ✓ Forward metrics calculated AFTER event end (no look-ahead)
  ✓ Entry point is NEXT bar after event (realistic execution)

Result: NO lookahead bias. Results are realistic for live trading.


PERFORMANCE TIPS
----------------

• For large datasets (>10M ticks), preprocessing may take 1-5 minutes
• Use vectorized numpy/pandas (no loops)
• No external libs beyond pandas/numpy/scipy
• Memory: ~5GB for 1 year EURUSD tick data (depends on tick frequency)


TROUBLESHOOTING
---------------

No events detected:
  → Thresholds too strict
  → Relax --tick_count_percentile, --range_percentile, --spread_percentile
  → Or reduce --compression_duration_min

NO-GO decision:
  → Effect size too small (ratio close to 1.0)
  → Effect inconsistent across years
  → Try different asset pair or time period
  → Revisit hypothesis (compression may not be edge)

CSV column errors:
  → Ensure MT5 export has 'time' (or 'datetime') and 'bid', 'ask' columns
  → Script auto-normalizes column names (case-insensitive)
  → If missing 'ask', script imputes as bid + 1 pip

