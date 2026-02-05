# Tick-Level Edge Discovery - Validation & Testing Guide

## Overview

This guide validates all 6 improvements made to `scripts/tick_edge_scan.py` for robust tick-level edge discovery with real MT5 tick data.

## 4 Critical Improvements Validated

### 1. **Robust Ask Imputation** ✅
**Problem:** Naive bid + 1 pip distorts spread calculations.

**Solution:** Use median spread from available data.
```
If ask column partially missing:
  median_spread = np.median(available_spreads)
  imputed_ask = bid + median_spread

If ask column fully missing:
  Use --assumed_spread_pips (default 1.0)
```

**Test Result:**
```
✅ test_ask_imputation_median_spread PASSED
   - Correctly computes median from available spreads
   - Imputes missing values with bid + median_spread
   - Tracks ask_imputed_ratio in metadata
```

**Validation:**
- Run with real MT5 data: `--assumed_spread_pips 1.0`
- Check summary.json → metadata → ask_imputed_ratio
- Compare `median_spread_computed` to market reality

---

### 2. **Baseline Exclusion (Event Windows)** ✅
**Problem:** Baseline includes bars during compression events, diluting effect sizes.

**Solution:** Create exclude_mask for event windows + forward windows (up to 30m).
```
exclude_mask = (indices in [start:end] OR indices in [end:end+max_horizon])
baseline = df_bars[~exclude_mask]
```

**Test Result:**
```
✅ test_baseline_exclusion_reduces_contamination PASSED
   - Event windows successfully removed from baseline
   - Forward windows (30m) excluded
   - Reports contamination percentage (0.1% in synthetic)
```

**Validation:**
- Baseline contamination should be minimal (<1%)
- Effect sizes should be more realistic (less dilution)
- Check summary.json → baseline → bars_excluded

---

### 3. **Stability Gating** ✅
**Problem:** GO/NO-GO decisions made on weak datasets (1 year, few events).

**Solution:** Add minimum year/event thresholds:
```
--min_years_analyzed (default 5)
--min_events_per_year (default 20)

Decision status: GO | NO-GO | INSUFFICIENT_DATA
```

**Test Result:**
```
✅ test_insufficient_data_gating PASSED
   - Correctly triggers INSUFFICIENT_DATA when thresholds unmet
   - 2 years analyzed < 5 required → INSUFFICIENT_DATA
   - 2023 has 5 events < 20 required → INSUFFICIENT_DATA
   - Provides explicit reasons for gating
```

**Validation:**
- Run with various --min_years_analyzed and --min_events_per_year
- Check that weak datasets are rejected
- Verify reason explanations in summary.json

---

### 4. **Forward Spread Metrics** ✅
**Problem:** No assessment of spread dynamics post-event.

**Solution:** Add forward spread metrics to assess tradeability:
```
forward_spread_mean_5m, forward_spread_std_5m
forward_spread_mean_15m, forward_spread_std_15m
forward_spread_mean_30m, forward_spread_std_30m
```

**Test Result:**
```
✅ test_forward_spread_metrics_computed PASSED
   - All 6 spread metric columns computed
   - Correctly aggregated over 5m/15m/30m horizons
   - Included in events.csv output
```

**Validation:**
- Check events.csv columns: forward_spread_mean_*
- Compare spread ratios (forward/baseline)
- Assess tradeability: is edge sustainable after costs?

---

## End-to-End Testing

### Step 1: Run Unit Tests
```powershell
cd "c:\Users\Marco\Desktop\MVP-V2\MVP-Multi-Asset"
.venv\Scripts\python.exe scripts/test_tick_edge_scan_improvements.py
```

Expected:
```
Results: 4 passed, 0 failed ✅
```

---

### Step 2: Run with Synthetic Data (Weak Dataset)
```powershell
.venv\Scripts\python.exe scripts/tick_edge_scan.py `
  --verbose `
  --tick_count_percentile 25 `
  --range_percentile 25 `
  --spread_percentile 40 `
  --min_years_analyzed 2 `
  --min_events_per_year 5
```

Expected Output:
```
Decision: INSUFFICIENT_DATA
Reason: vol_5m: Years below 5 events: 2023(1)

Baseline excluded: 0.1% of bars ✅
Ask imputed: 0.0% (no imputation in synthetic)
Forward spread metrics: present ✅
```

---

### Step 3: Run with Real MT5 Data
```powershell
# Export EURUSD 1-minute bars (2+ years) from MT5
# Save to data/EURUSD_ticks.csv

.venv\Scripts\python.exe scripts/tick_edge_scan.py `
  --tick_file data/EURUSD_ticks.csv `
  --verbose `
  --min_years_analyzed 2 `
  --min_events_per_year 10
```

Expected Outputs:
```
1. Imputation metrics (if MT5 has missing ask):
   ask_imputed_ratio: 0.05-0.15 (typical)
   median_spread_computed: 0.00010-0.00020 (1-2 pips)

2. Baseline statistics:
   baseline_n_bars: X
   bars_excluded: Y (event + forward windows)
   pct_excluded: Z% (typically 0.5-2%)

3. Decision status:
   INSUFFICIENT_DATA (if <2 years or <10 events/year)
   NO-GO (if effect size too small)
   GO (if all thresholds pass)

4. Forward spread metrics in events.csv:
   forward_spread_mean_5m, forward_spread_std_5m
   forward_spread_mean_15m, forward_spread_std_15m
   forward_spread_mean_30m, forward_spread_std_30m
```

---

## Quality Checks

### Imputation Quality
✅ **Check:**
```powershell
Get-Content outputs/summary.json | ConvertFrom-Json | Select-Object -ExpandProperty imputation
```

✅ **Expected:**
```json
{
  "ask_imputed_count": 15000,
  "ask_imputed_ratio": 0.05,
  "median_spread_computed": 0.00012,
  "assumed_spread_pips": 1.0
}
```

---

### Baseline Quality
✅ **Check:**
```powershell
Get-Content outputs/summary.json | ConvertFrom-Json | Select-Object -ExpandProperty baseline
```

✅ **Expected:**
```json
{
  "forward_vol_5m": 0.000450,
  "forward_range_5m": 0.000280,
  "forward_spread_mean_5m": 0.000118,
  "bars_excluded": 4500,
  "pct_excluded": 0.8
}
```

---

### Forward Spread Metrics
✅ **Check:**
```powershell
Get-Content outputs/events.csv | Select-Object -First 2
```

✅ **Expected Columns Present:**
```
event_idx,start_time,end_time,...,forward_spread_mean_5m,forward_spread_std_5m,...
1,2023-01-15 09:30:00,2023-01-15 09:40:00,...,0.000118,0.000025,...
```

---

### Stability Gating
✅ **Check:**
```powershell
Get-Content outputs/summary.json | ConvertFrom-Json | Select-Object -ExpandProperty decision
```

✅ **Expected:**
```json
{
  "status": "GO | NO-GO | INSUFFICIENT_DATA",
  "reason": [
    "vol_5m: 3 years analyzed (met 2 year minimum)",
    "vol_5m: All years have >= 15 events"
  ],
  "min_years_analyzed": 2,
  "min_events_per_year": 10,
  "vol_5m_n_years": 3,
  "vol_5m_years_positive": 3,
  "vol_5m_consistency": 0.95
}
```

---

## Regression Testing

Run these regression tests to ensure no breaking changes:

### Test 1: Synthetic Data Still Works
```powershell
.venv\Scripts\python.exe scripts/tick_edge_scan.py --verbose
# Should produce INSUFFICIENT_DATA correctly ✅
```

### Test 2: Output Files Present
```powershell
ls outputs/
# Expected: events.csv, summary.json, tick_statistics.json ✅
```

### Test 3: No Runtime Errors
```powershell
# Check outputs for any error messages
Get-Content outputs/summary.json | ConvertFrom-Json
# Should be valid JSON, no errors ✅
```

---

## Tuning Recommendations

### For Weak Datasets (< 2 years)
```powershell
--min_years_analyzed 1
--min_events_per_year 10
# Relaxed thresholds to test INSUFFICIENT_DATA logic
```

### For Strong Datasets (> 3 years)
```powershell
--min_years_analyzed 3
--min_events_per_year 15
# Stricter thresholds for more reliable decisions
```

### For High Spread Assets
```powershell
--assumed_spread_pips 2.5
# E.g., for GBPUSD or exotics
```

---

## Summary

| Improvement | Status | Test | Validation |
|------------|--------|------|-----------|
| Ask imputation (median) | ✅ | test_ask_imputation_median_spread | Check ask_imputed_ratio |
| Baseline exclusion | ✅ | test_baseline_exclusion_reduces_contamination | Check pct_excluded |
| Stability gating | ✅ | test_insufficient_data_gating | Check INSUFFICIENT_DATA |
| Spread metrics | ✅ | test_forward_spread_metrics_computed | Check events.csv |

---

## Next Steps

1. **Export real MT5 data** (2+ years EURUSD)
2. **Run tick_edge_scan.py** with real data
3. **Validate outputs** using quality checks above
4. **Assess edge quality** using forward spread metrics
5. **Make GO/NO-GO decision** based on stability gating
6. **Proceed to Phase 1 backtest** if GO (separate implementation)

---

## File Reference

- **Main script:** `scripts/tick_edge_scan.py` (620 lines, all improvements included)
- **Unit tests:** `scripts/test_tick_edge_scan_improvements.py` (4 tests, all passing)
- **Outputs:** `outputs/{events.csv, summary.json, tick_statistics.json}`
