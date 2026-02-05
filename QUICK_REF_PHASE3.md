# Quick Reference - Tick-Level Edge Discovery (Phase 3)

## 🚀 Quick Start

### 1. Run Unit Tests
```powershell
.venv\Scripts\python.exe scripts/test_tick_edge_scan_improvements.py
```
Expected: `4 passed, 0 failed` ✅

### 2. Run with Synthetic Data
```powershell
.venv\Scripts\python.exe scripts/tick_edge_scan.py --verbose
```
Expected: `INSUFFICIENT_DATA` (2023 has 1 event < 5 required) ✅

### 3. Run with Real MT5 Data
```powershell
.venv\Scripts\python.exe scripts/tick_edge_scan.py `
  --tick_file data/EURUSD_ticks.csv `
  --verbose `
  --min_years_analyzed 2 `
  --min_events_per_year 10
```

---

## 🔧 Key Arguments

```powershell
# Data Quality
--assumed_spread_pips 1.0           # Default spread if ask missing

# Stability Gating
--min_years_analyzed 5              # Min years for GO decision
--min_events_per_year 20            # Min events/year for GO decision

# Event Detection
--tick_count_percentile 75          # Threshold for high-tick bars
--range_percentile 75               # Threshold for high-range bars
--spread_percentile 75              # Threshold for wide-spread bars

# Effect Size Thresholds
--vol_ratio_threshold 1.05          # Min vol ratio for GO
--range_ratio_threshold 1.05        # Min range ratio for GO
--spread_ratio_threshold 0.95       # Min spread ratio for GO
```

---

## 📊 Output Files

### events.csv
All compression events with metrics:
- `forward_spread_mean_5m`, `forward_spread_std_5m` (5-min spreads)
- `forward_spread_mean_15m`, `forward_spread_std_15m` (15-min spreads)
- `forward_spread_mean_30m`, `forward_spread_std_30m` (30-min spreads)

### summary.json
```json
{
  "metadata": { "ask_imputed_ratio": 0.0, ... },
  "imputation": {
    "ask_imputed_ratio": 0.0,
    "median_spread_computed": null,
    "assumed_spread_pips": 1.0
  },
  "baseline": { "forward_vol_5m": ..., "pct_excluded": 0.1 },
  "decision": {
    "status": "GO | NO-GO | INSUFFICIENT_DATA",
    "reason": [...]
  }
}
```

---

## ✅ Validation Checklist

### Ask Imputation
- [ ] Check `summary.json` → `imputation` → `ask_imputed_ratio`
- [ ] Compare `median_spread_computed` to market spreads

### Baseline Quality
- [ ] Check `summary.json` → `baseline` → `pct_excluded`
- [ ] Expected: < 2% (event windows removed)

### Spread Metrics
- [ ] Check `events.csv` has `forward_spread_mean_*` columns
- [ ] Verify all events have spread statistics

### Stability Gating
- [ ] Check `summary.json` → `decision` → `status`
- [ ] If `INSUFFICIENT_DATA`: check reason (years or events below threshold)

---

## 🎯 Decision Rules

### GO Decision
✅ `vol_ratio_5m >= 1.05` (effect size significant)
✅ `vol_consistency >= 0.80` (edge stable across years)
✅ `n_years >= min_years_analyzed` (sufficient data)
✅ All years have `>= min_events_per_year` events

### NO-GO Decision
❌ `vol_ratio_5m < 1.05` (effect too small)
❌ `vol_consistency < 0.80` (edge inconsistent)

### INSUFFICIENT_DATA Decision
⚠️ `n_years < min_years_analyzed` (not enough years)
⚠️ Some years have `< min_events_per_year` events

---

## 📈 Expected Metrics (Real MT5 Data)

| Metric | Range | Status |
|--------|-------|--------|
| ask_imputed_ratio | 0.05-0.15 | ✅ Normal |
| median_spread_computed | 0.0001-0.0003 | ✅ Market spreads |
| pct_excluded | 0.5-2.0% | ✅ Events removed |
| vol_ratio_5m | 1.02-1.30 | ✅ Typical effect |
| vol_consistency | 0.70-0.95 | ✅ Stable across years |

---

## 🐛 Troubleshooting

### ask_imputed_ratio = 0.0
**Issue:** Expected imputation but got none
**Solution:** MT5 export has complete ask data (no issue) ✅

### pct_excluded > 5%
**Issue:** Too many bars excluded
**Solution:** Many events detected, baseline heavily contaminated
**Fix:** Increase `--min_years_analyzed` threshold

### Decision = INSUFFICIENT_DATA
**Issue:** Not enough data
**Solution:** Collect more data (need 3+ years, 15+ events/year)
**Workaround:** Relax thresholds temporarily: `--min_years_analyzed 2 --min_events_per_year 10`

### vol_consistency < 0.70
**Issue:** Edge inconsistent
**Reason:** Effect varies significantly across years
**Solution:** NO-GO decision is correct

---

## 📚 Documentation

- **IMPROVED_SCANNER_GUIDE.md** - Complete reference guide
- **TESTING_GUIDE.md** - End-to-end testing procedures
- **PHASE3_CHECKLIST.md** - Implementation checklist

---

## 4 Key Improvements

### 1. Ask Imputation
**Before:** bid + 1 pip (naive)
**After:** bid + median_spread (robust)
**Impact:** Accurate spread calculations

### 2. Baseline Exclusion
**Before:** Baseline contaminated by event windows
**After:** Event + forward windows excluded
**Impact:** More conservative effect sizes

### 3. Stability Gating
**Before:** GO/NO-GO on any dataset
**After:** INSUFFICIENT_DATA for weak datasets
**Impact:** Prevents false positives

### 4. Spread Metrics
**Before:** No tradeability assessment
**After:** forward_spread_mean/std per event
**Impact:** Can assess if edge survives costs

---

## ⚡ One-Liner Commands

```powershell
# Test
.venv\Scripts\python.exe scripts/test_tick_edge_scan_improvements.py

# Synthetic
.venv\Scripts\python.exe scripts/tick_edge_scan.py --verbose

# Real Data (2-year minimum)
.venv\Scripts\python.exe scripts/tick_edge_scan.py --tick_file data/EURUSD_ticks.csv --min_years_analyzed 2 --min_events_per_year 10 --verbose

# Check outputs
gc outputs/summary.json | ConvertFrom-Json
gc outputs/events.csv | Select-Object -First 2
```

---

## Next Steps

1. Export EURUSD 1-min ticks (2+ years) from MT5
2. Run with real data
3. Validate using checklist above
4. If GO: Proceed to Phase 1 backtest
5. If NO-GO: Analyze why effect too small
6. If INSUFFICIENT_DATA: Collect more data

---

**Version:** 2.0 (Phase 3 - Production Ready)
**Status:** ✅ All 4 improvements complete and tested
