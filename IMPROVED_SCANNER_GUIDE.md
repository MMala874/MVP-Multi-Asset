# Improved Tick-Level Edge Discovery Scanner
## Complete Reference & Deployment Guide

---

## Executive Summary

The `scripts/tick_edge_scan.py` scanner has been enhanced with **4 critical improvements** for production-ready tick-level edge discovery on real MT5 data:

1. **Robust Ask Imputation** - Uses median spread instead of naive 1 pip
2. **Baseline Exclusion** - Removes event windows to prevent contamination
3. **Stability Gating** - Rejects weak datasets with INSUFFICIENT_DATA status
4. **Forward Spread Metrics** - Assesses tradeability and costs

**Status:** ✅ All improvements implemented, unit tested, and production-ready

---

## Installation & Setup

### Prerequisites
```powershell
cd c:\Users\Marco\Desktop\MVP-V2\MVP-Multi-Asset
.venv\Scripts\python.exe -m pip install numpy pandas scipy pyyaml
```

### Verify Installation
```powershell
.venv\Scripts\python.exe scripts/tick_edge_scan.py --help
```

---

## Quick Start

### Run with Synthetic Data (Testing)
```powershell
.venv\Scripts\python.exe scripts/tick_edge_scan.py --verbose
```

Expected: `Decision: INSUFFICIENT_DATA` (correct - only 2023 data)

### Run with Real MT5 Data
```powershell
# 1. Export EURUSD 1-minute bars (2+ years) from MT5
# 2. Save to data/EURUSD_ticks.csv

.venv\Scripts\python.exe scripts/tick_edge_scan.py `
  --tick_file data/EURUSD_ticks.csv `
  --verbose `
  --min_years_analyzed 2 `
  --min_events_per_year 10
```

---

## Command-Line Arguments

### Input/Output
```
--tick_file          Path to tick data CSV (default: data/ticks.csv)
--output_dir         Output directory (default: outputs/)
--verbose            Print verbose output (default: False)
```

### Data Quality (NEW)
```
--assumed_spread_pips    Default spread if ask column missing (default: 1.0)
```

### Stability Gating (NEW)
```
--min_years_analyzed     Min years required (default: 5)
--min_events_per_year    Min events per year required (default: 20)
```

### Event Detection
```
--tick_count_percentile  Threshold for high-tick bars (default: 75)
--range_percentile       Threshold for high-range bars (default: 75)
--spread_percentile      Threshold for wide-spread bars (default: 75)
--max_event_duration_min Max event duration in minutes (default: 60)
```

### Effect Size Thresholds
```
--vol_ratio_threshold    Min vol effect ratio for GO (default: 1.05)
--range_ratio_threshold  Min range effect ratio for GO (default: 1.05)
--spread_ratio_threshold Min spread effect ratio for GO (default: 0.95)
```

---

## Key Improvements Explained

### 1. Robust Ask Imputation

**Problem:** Many tick datasets have missing ask values. Naive imputation (bid + 1 pip) doesn't match market reality.

**Solution:** 
```python
# Compute median spread from available ask values
available_spreads = (df['ask'] - df['bid']).dropna()
median_spread = available_spreads.median()

# Impute missing ask values
df.loc[df['ask'].isna(), 'ask'] = df.loc[df['ask'].isna(), 'bid'] + median_spread

# Track in metadata
ask_imputed_ratio = (df['ask'].isna()).sum() / len(df)
```

**Validation:**
- Check `summary.json` → `imputation` → `ask_imputed_ratio`
- For real MT5: expect 5-15% imputation (typical)
- Compare `median_spread_computed` to market spreads

---

### 2. Baseline Exclusion (Event Windows)

**Problem:** Baseline includes bars during compression events, which inflates effect sizes.

**Solution:**
```python
# Create mask excluding event windows + forward windows (30m)
exclude_mask = pd.Series(False, index=df_bars.index)
for event in events:
    start, end = event['start_idx'], event['end_idx']
    forward_end = min(end + max_horizon_min, len(df_bars))
    exclude_mask.iloc[start:forward_end] = True

# Compute baseline on clean bars only
baseline = df_bars[~exclude_mask].mean()
```

**Validation:**
- Check `summary.json` → `baseline` → `pct_excluded`
- Expected: 0.5-2% bars excluded (event + forward windows)
- Effect sizes should be more conservative

---

### 3. Stability Gating (Data Quality)

**Problem:** GO/NO-GO decisions made on weak datasets (1 year, 5 events).

**Solution:**
```python
# Filter years below minimum event count
qualifying_years = [
    y for y in stability_per_year[metric] 
    if y['n_events'] >= min_events_per_year
]

# Check thresholds
if len(qualifying_years) < min_years_analyzed:
    status = "INSUFFICIENT_DATA"
    reason = f"Only {len(qualifying_years)} years (need {min_years_analyzed})"
else:
    status = "GO" | "NO-GO"  # Based on effect size
```

**Validation:**
- Check `summary.json` → `decision` → `status`
- Expected values: "GO" | "NO-GO" | "INSUFFICIENT_DATA"
- Reasons explain why INSUFFICIENT_DATA (if applicable)

---

### 4. Forward Spread Metrics

**Problem:** No way to assess if edge is tradeable (spreads could widen post-event).

**Solution:**
```python
# Compute spread metrics over 5m/15m/30m windows
forward_spread_mean_5m = df_bars[end_idx:end_idx+5].spread_mean.mean()
forward_spread_std_5m = df_bars[end_idx:end_idx+5].spread_std.mean()

# Repeat for 15m and 30m windows
# Compute spread ratio effect sizes
spread_ratio = forward_spread_mean / baseline_spread_mean
```

**Validation:**
- Check `events.csv` columns: `forward_spread_mean_*`, `forward_spread_std_*`
- Assess tradeability:
  - If forward_spread > baseline_spread: worse conditions
  - If edge profit < forward_spread: unprofitable

---

## Output Files

### 1. events.csv
```
event_idx,start_time,end_time,duration_min,tick_count,range_bps,...,
forward_return_mean_5m,forward_vol_5m,forward_spread_mean_5m,...
```

**New columns (Phase 3):**
- `forward_spread_mean_5m`, `forward_spread_std_5m`
- `forward_spread_mean_15m`, `forward_spread_std_15m`
- `forward_spread_mean_30m`, `forward_spread_std_30m`

**Use for:** Assessing tradeability of each edge event

---

### 2. summary.json
```json
{
  "metadata": {
    "data_file": "...",
    "n_ticks": 500000,
    "n_bars": 300000,
    "time_range": "2023-01-01 to 2024-12-31",
    "ask_imputed_ratio": 0.08
  },
  "imputation": {
    "ask_imputed_count": 40000,
    "ask_imputed_ratio": 0.08,
    "median_spread_computed": 0.00012,
    "assumed_spread_pips": 1.0
  },
  "baseline": {
    "forward_vol_5m": 0.000450,
    "forward_range_5m": 0.000280,
    "forward_spread_mean_5m": 0.000118,
    "bars_excluded": 4500,
    "pct_excluded": 0.8
  },
  "decision": {
    "status": "GO | NO-GO | INSUFFICIENT_DATA",
    "reason": [
      "vol_5m: 3 years analyzed (met 2 year minimum)",
      "vol_5m: All years have >= 10 events"
    ],
    "min_years_analyzed": 2,
    "min_events_per_year": 10,
    "vol_5m_effect_ratio": 1.12,
    "vol_5m_consistency": 0.87
  }
}
```

**Key sections for validation:**
- `imputation`: Check ask_imputed_ratio and median_spread_computed
- `baseline`: Check pct_excluded (should be <2%)
- `decision`: Check status and reason

---

## Workflow Recommendations

### Phase 1: Unit Testing
```powershell
.venv\Scripts\python.exe scripts/test_tick_edge_scan_improvements.py
```
Expected: `4 passed, 0 failed`

---

### Phase 2: Synthetic Data Testing
```powershell
.venv\Scripts\python.exe scripts/tick_edge_scan.py --verbose
```
Expected: `INSUFFICIENT_DATA` (only 2023 has limited events)

---

### Phase 3: Real MT5 Data (Weak Dataset)
```powershell
.venv\Scripts\python.exe scripts/tick_edge_scan.py `
  --tick_file data/EURUSD_2years.csv `
  --verbose `
  --min_years_analyzed 2 `
  --min_events_per_year 10
```

**Expected Outcomes:**
- If `INSUFFICIENT_DATA`: Collect more data (need 3+ years, 15+ events/year)
- If `NO-GO`: Edge effect size too small
- If `GO`: Proceed to Phase 1 backtest

---

### Phase 4: Real MT5 Data (Strong Dataset)
```powershell
.venv\Scripts\python.exe scripts/tick_edge_scan.py `
  --tick_file data/EURUSD_5years.csv `
  --verbose `
  --min_years_analyzed 3 `
  --min_events_per_year 15
```

**Expected for GO Decision:**
- ✅ 3+ years analyzed
- ✅ All years have 15+ events
- ✅ vol_5m_effect_ratio > 1.05
- ✅ vol_5m_consistency > 0.80
- ✅ Spread metrics reasonable (not widening post-event)

---

### Phase 5: Proceed to Backtest (if GO)
Once GO decision reached:
```powershell
# Create backtest config
# Run Phase 1 backtest (separate implementation)
# Validate OOS performance
# Paper trade if OOS passes
# Live deploy if paper passes
```

---

## Troubleshooting

### Issue: ask_imputed_ratio = 0.0 but expect > 0
**Cause:** MT5 exports complete ask data (no imputation needed)
**Action:** No issue - system working correctly

### Issue: pct_excluded > 5%
**Cause:** Many compression events detected, baseline heavily contaminated
**Action:** Consider larger max_horizon_min (30m → 60m) to exclude longer forward windows

### Issue: Decision = INSUFFICIENT_DATA
**Cause:** Dataset too weak (< min_years_analyzed or < min_events_per_year)
**Action:** Either collect more data or relax thresholds (--min_years_analyzed 2)

### Issue: vol_5m_consistency < 0.70
**Cause:** Edge inconsistent across years
**Action:** Edge unreliable - NO-GO is correct decision

### Issue: forward_spread_std > baseline_spread_mean
**Cause:** Spreads widen significantly post-event
**Action:** Edge unprofitable - NO-GO is correct decision

---

## Performance Expectations

| Metric | Typical Range | Comment |
|--------|---------------|---------|
| ask_imputed_ratio | 0.00-0.15 | Depends on MT5 export quality |
| pct_excluded | 0.5-2.0% | Event windows + forward windows |
| vol_5m_effect_ratio | 1.02-1.30 | Effect size (must be > 1.05 for GO) |
| vol_5m_consistency | 0.70-0.95 | Stability across years (must be > 0.80) |
| forward_spread_mean | 0.0001-0.0003 | Market-dependent (EURUSD: ~1.5 pips) |

---

## File Locations

| File | Location | Purpose |
|------|----------|---------|
| Main script | `scripts/tick_edge_scan.py` | Core scanner implementation |
| Unit tests | `scripts/test_tick_edge_scan_improvements.py` | Validation of all improvements |
| Test guide | `TESTING_GUIDE.md` | End-to-end testing procedures |
| Output: events | `outputs/events.csv` | Edge events with metrics |
| Output: summary | `outputs/summary.json` | Decision + metadata |
| Sample data | `data/ticks.csv` | Synthetic tick data |

---

## Next Steps

1. **Export real EURUSD tick data** from MT5 (2+ years)
2. **Run scanner** with real data: `scripts/tick_edge_scan.py --tick_file data/EURUSD_ticks.csv --verbose`
3. **Validate outputs** using quality checks in TESTING_GUIDE.md
4. **Assess edge** using forward spread metrics
5. **Make decision** based on stability gating (GO/NO-GO/INSUFFICIENT_DATA)
6. **Proceed to Phase 1 backtest** if GO (separate implementation)

---

## Support & Questions

All improvements are integrated into `scripts/tick_edge_scan.py`. No additional dependencies required beyond numpy, pandas, scipy.

For issues:
1. Check TESTING_GUIDE.md for quality checks
2. Review troubleshooting section above
3. Run unit tests: `test_tick_edge_scan_improvements.py`
4. Review summary.json for detailed diagnostics

---

**Version:** 2.0 (Phase 3 - Production Ready)
**Status:** ✅ All improvements implemented, tested, and ready for real MT5 data
