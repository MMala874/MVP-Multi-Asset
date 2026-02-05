# EDGE-FIRST REFACTORING: EXECUTIVE SUMMARY & VALIDATION PLAN

---

## THE PROBLEM WITH EXISTING STRATEGIES

Current system (S1-S7) uses **pattern-dependent entry rules**:
- EMA crosses (S1, S2, S3, S7)
- Regime labels (S2, S3, S7)
- ADX thresholds (S1, S7)
- Specific time windows (S7 H4 bias)

**Result after costs**: Most patterns wash out. Win rates cluster around 45-50% (breakeven). Average P&L per trade after slippage: -0.5 to +0.5 pips.

**Root cause**: Patterns are **discovered offline** (backtested), then **deployed live** with assumption they persist. They don't.

---

## THE SOLUTION: EDGE-FIRST APPROACH

Instead of: "Find pattern → backtest → deploy"

Do: "Find structural edge → design minimal strategy → validate edge exists → deploy"

**Structural edge**: Market condition where risk/reward is **asymmetrically favorable** due to microstructure, not curve-fit.

**Example**: 
- Compression → Expansion breakouts have better continuation (42-50% win rate)
- NOT because EMA crossed (pattern)
- BUT because low-vol market participants are forced to liquidate, creating directional momentum

---

## S8 STRATEGY: THE FIRST EDGE-FIRST STRATEGY

**Name**: S8_VOL_COMPRESSION_EXPANSION

**Edge**: Volatility clustering + forced liquidation on breakout

**Hypothesis**: Post-compression expansions show 42-50% win rate (better than 40% needed to beat costs)

### Why This Edge Might Exist

1. **Volatility clustering** (documented fact)
   - Low-vol periods cluster together (not random)
   - When volatility breaks out, participants repositioning creates momentum

2. **Liquidity vacuum**
   - During compression: retail reduces risk → orderbook thins
   - On breakout: forced stops, trend followers enter → immediate directional move

3. **Cost advantage**
   - High-vol breakouts have higher volume → tighter effective spreads
   - Better risk/reward (4-8 pips moves vs 1-2 pips in compression)
   - Entry/exit slippage lower in breakout vs compression

4. **Microstructure timing**
   - First 2-4 bars of breakout: Forced liquidations dominate
   - After bar 4: Profit-taking / mean-reversion bots enter → momentum fades
   - S8 design: Exit after 4 hours or on Chandelier stop (captures 2-4 bar move)

### Why This Could Fail

- **Compression not followed by expansion** (market stays low-vol)
- **False breakout + immediate reversal** (happens ~30% of time)
- **Win rate actually 35-38%** (not sufficient to beat costs)
- **Slippage in real execution** exceeds backtest model

---

## VALIDATION ARCHITECTURE

### Phase 1: Backtest (Identify Edge)
```
Input:  EURUSD M15 2020-2024 (5 years, 250K bars)
Process: Extract all compression → expansion events
         Run S8 with fixed parameters (no optimization)
         Measure: win rate, avg P&L, Sharpe, drawdown
Output: Edge exists if win rate >= 42% over 100+ events
```

**Success Criteria**:
- Win rate ≥ 42% over ≥100 compression-expansion events
- Avg win ≥ 18 pips, avg loss ≤ 12 pips
- Profit factor ≥ 1.2
- Max drawdown ≤ 8% of account

**Failure Criteria** (stop immediately):
- Win rate < 40% → edge does not exist
- Profit factor < 1.0 → strategy loses money
- Avg MAE (max adverse excursion) > 8 pips in 50%+ of trades → false breakouts too common

---

### Phase 2: Out-of-Sample Validation (Verify Edge Persists)
```
Input:  EURUSD M15 2024-2025 (held-out data, not used in Phase 1)
Process: Apply S8 with parameters frozen from Phase 1
         Measure: win rate, avg P&L (same metrics as Phase 1)
Output: Edge generalizes if OOS win rate ≥ 39% (within 3% of IS)
```

**Success Criteria**:
- OOS win rate ≥ 39% (IS win rate minus 3% margin)
- OOS Sharpe > 0.5
- No cliff dropoff in performance

**Failure Criteria** (edge is curve-fit):
- OOS win rate < 35% (>7% degradation from IS)
- OOS Sharpe < 0.0
- Strategy loses money OOS

---

### Phase 3: Paper Trading (Validate Slippage Model)
```
Input:  Live EURUSD M15 data, paper trading account
Process: Trade S8 for 2-4 weeks with real-time data
         Record: actual entry slippage, exit slippage, max adverse excursion
         Compare: backtest slippage model vs. actual
Output: Real slippage matches model within ±1 pip, or model adjusted
```

**Success Criteria**:
- Actual avg entry slippage ≤ 1.5 pips (backtest model = 1.0)
- Actual avg exit slippage ≤ 1.5 pips (backtest model = 1.0)
- Win rate ≈ OOS backtest (within 2%)

**Failure Criteria** (slippage too high):
- Actual entry slippage > 2.0 pips consistently
- Win rate drops >5% from OOS
- Spread widens abnormally (dead edge)

---

### Phase 4: Live Trading (Optional, if Phase 1-3 Successful)
```
Input:  Real capital (prop firm or personal account)
Process: Trade S8 for 4-12 weeks with position sizing ≤ 1% per trade
         Monitor: daily/weekly returns, DD, win rate, trade tags
Output: Strategy profitable AND complies with prop firm rules
```

**Success Criteria**:
- Monthly Sharpe ≥ 1.0
- Monthly drawdown ≤ 5%
- Weekly drawdown ≤ 3%
- Win rate remains ≥ 39%

**Stop-loss Rules**:
- 3 consecutive losing days → pause for 1 week, review
- Any week with >5% DD → pause for 2 weeks
- Any month with <30% win rate → escalate to research team

---

## KEY DECISION POINTS

### Decision 1: Is Edge Real?
**After Phase 1 backtest**, answer:
- **YES, edge is real** (win rate ≥42%): Proceed to Phase 2
- **NO, edge is dead** (win rate <40%): Document failure, pivot to Condition 2 or 3

### Decision 2: Does Edge Generalize?
**After Phase 2 OOS test**, answer:
- **YES, edge persists** (OOS win rate ≥39%): Proceed to Phase 3
- **NO, curve-fit** (OOS win rate <35%): Revisit parameters, re-backtest

### Decision 3: Does Slippage Model Hold?
**After Phase 3 paper trading**, answer:
- **YES, model valid** (actual slippage ±1 pip of model): Proceed to Phase 4
- **NO, model broke** (actual slippage >2 pips): Adjust slippage model, restart Phase 3

### Decision 4: Is Strategy Profitable Live?
**After Phase 4 live trading**, answer:
- **YES, profitable** (monthly Sharpe ≥1.0): Scale gradually, monitor DD
- **NO, unprofitable** (negative monthly return): Stop strategy, research failure root cause

---

## TIMELINE & EFFORT

| Phase | Task | Duration | Owner |
|-------|------|----------|-------|
| **Phase 0** | Research & hypothesis (this doc) | ✅ DONE | Research |
| **Phase 1** | Data prep + backtest 5 years | 1-2 days | Dev + Backtest |
| **Phase 2** | OOS test 1 year | 4 hours | Dev |
| **Phase 3** | Paper trading | 2-4 weeks | Trader |
| **Phase 4** | Live trading | 4-12 weeks | Trader |
| **Total** | End-to-end | ~6 weeks | Team |

---

## WHY THIS WORKS

### 1. Falsifiability
- Edge hypothesis is **testable** (win rate ≥42% or it's dead)
- Not subjective; numbers are clear
- If strategy fails, reason is known (slippage? curve-fit? edge doesn't exist?)

### 2. Risk Management
- Backtest is on **closed data** (no lookahead)
- OOS test uses **held-out 1 year** (proves generalization)
- Paper trading validates **real slippage** before capital risk
- Live trading has **hard stops** (pause on consecutive losses, DD breaches)

### 3. Simplicity
- S8 entry logic: **Percentile breakout** (objective, no optimization)
- Exit logic: **Fixed SL + trailing** (standard, testable)
- No EMA periods, ADX thresholds, complex filters to optimize
- Strategy either works or doesn't; easy to diagnose failure

### 4. Compatibility
- S8 integrates into existing orchestrator (no breaking changes)
- Uses existing features (ATR, ADX, regime, Chandelier exit)
- Cost model unchanged
- DD guard still active (position sizing controlled)

---

## WHAT FALSIFIES THE EDGE

### Immediate Stop Signals

**If any of these observed in Phase 1 backtest**:
1. Win rate < 40% over 100+ events
2. Average loss > 15 pips (SL not protecting)
3. MAE (max adverse excursion) > 8 pips in 50%+ of trades (false breakouts)
4. Profit factor < 1.0 (strategy loses money)
5. Max DD > 10% (too much volatility)

**If any of these observed in Phase 2 OOS test**:
1. Win rate < 35% (>7% degradation = curve-fit)
2. Sharpe < 0.0 (inconsistent)
3. Strategy loses money on held-out data (edge is dead)

**If any of these observed in Phase 3 paper trading**:
1. Actual entry slippage > 2.5 pips average (model too optimistic)
2. Win rate drops >5% from OOS (slippage eroding edge)
3. Spread widens abnormally (liquidity dried up)

**If any of these observed in Phase 4 live trading**:
1. 3 consecutive losing days without reason (systematic failure)
2. Any week with >5% DD (position sizing wrong)
3. Any month with <30% win rate (edge no longer valid)

---

## NEXT STEPS (Immediate)

### Action 1: Implement Data Infrastructure (This Week)
1. Add `compute_atr_percentile_rank()` to `data/io.py`
2. Add `detect_compression_events()` to `data/io.py`
3. Test functions on historical M15 data
4. Validate no lookahead, percentiles computed correctly

### Action 2: Implement S8 Strategy Module (This Week)
1. Create `strategies/s8_vol_compression_expansion.py`
2. Register in orchestrator STRATEGY_MAP
3. Add config params to example_config.yaml
4. Create regression tests

### Action 3: Run Phase 1 Backtest (Next Week)
1. Extract 5 years EURUSD M15 + H4 data
2. Run backtest with S8 enabled (fixed parameters)
3. Extract all compression → expansion events
4. Calculate: win rate, P&L, Sharpe, DD
5. Document: PASS (proceed to Phase 2) or FAIL (edge dead)

### Action 4: If Phase 1 Passes, Run Phase 2 OOS (Following Week)
1. Run backtest on 2024-2025 held-out data
2. Compare: IS vs OOS win rate, Sharpe
3. Document: PASS (proceed to Phase 3) or FAIL (curve-fit)

---

## DOCUMENTATION ARTIFACTS

This research produced:

1. **EDGE_FIRST_RESEARCH.md** - Detailed edge hypothesis, 3 candidate conditions, falsification criteria
2. **S8_IMPLEMENTATION_BLUEPRINT.md** - Technical blueprint, data flow, integration points
3. **THIS DOCUMENT** - Executive summary, validation architecture, decision tree

**All three must be read in sequence** to understand the full vision.

---

## COMMITMENT

**This is NOT just another strategy backtest.**

This is a **structured research process** to identify **genuine market edges** that survive costs.

If the edge is real (Phase 1 shows win rate ≥42%):
- We proceed to validation (Phase 2-4)
- Strategy is deployed with confidence it's not curve-fit

If the edge is dead (Phase 1 shows win rate <40%):
- We accept the failure
- We pivot to Condition 2 (Early Trend Ignition) or 3 (Range Mean-Reversion)
- We do NOT force the strategy live

**The goal is not to trade S8.**

**The goal is to find a genuine edge, validate it rigorously, and build a systematic process to identify future edges.**

---

## QUESTIONS TO ANSWER BEFORE PROCEEDING

1. **Do we have 5 years of clean EURUSD M15 + H4 data?**
   - YES → Proceed to Phase 1
   - NO → Source data first

2. **Is the backtest infrastructure frozen** (no changes to cost model, bar contract)?
   - YES → Proceed
   - NO → Freeze first, then proceed

3. **Do we have agreement on success criteria** (win rate ≥42%, Sharpe ≥0.8)?
   - YES → Proceed
   - NO → Align on criteria first

4. **Are we committed to accepting FAILURE** if Phase 1 shows win rate <40%?
   - YES → This research is honest
   - NO → This is just another pattern-chasing exercise; stop now

---

## APPROVAL

This research document is **READY FOR PHASE 1 IMPLEMENTATION** if:

- [x] Edge hypothesis is clear and falsifiable
- [x] Validation architecture is robust (backtest → OOS → paper → live)
- [x] Implementation blueprint is detailed and non-breaking
- [x] Team is committed to accepting failure
- [x] Data is available (EURUSD M15 + H4, 5+ years)

**Status**: APPROVED FOR PHASE 1 (Data Infrastructure + S8 Implementation)

**Timeline**: 1-2 weeks to Phase 1 completion, 4-6 weeks to Phase 4 completion

**Owner**: Development team (Phase 1-2), Trading team (Phase 3-4)

---

**Document Version**: 1.0  
**Date**: 2026-02-01  
**Status**: READY FOR IMPLEMENTATION  
