# EDGE-FIRST TRADING SYSTEM REFACTORING

## Complete Research Package & Implementation Guide

**Date**: February 1, 2026  
**Status**: READY FOR PHASE 1 IMPLEMENTATION  
**Asset**: EURUSD only (M15/H1/H4)

---

## DOCUMENT OVERVIEW

This package contains 5 interconnected research documents that define a complete refactoring of the trading system from **pattern-chasing to edge-first design**.

### Document Dependencies

```
1. EDGE_FIRST_RESEARCH.md (Main Document)
   ├─ Problem: Pattern-based strategies fail post-costs
   ├─ Solution: Find structural market edges
   ├─ Candidates: 3 potential edges evaluated
   ├─ Recommended: S8_VOL_COMPRESSION_EXPANSION
   └─ Why this edge works: Volatility clustering + forced liquidation
   
   → Read this FIRST to understand the vision

2. S8_IMPLEMENTATION_BLUEPRINT.md (Technical Design)
   ├─ How to integrate S8 into existing infrastructure
   ├─ Data functions needed: percentile rank, compression detection
   ├─ Strategy logic: entry/exit/gating
   ├─ Code flow: data → features → signal → backtest
   └─ Exactly how to NOT break existing system
   
   → Read this SECOND for technical details

3. EDGE_FIRST_SUMMARY.md (Executive Overview)
   ├─ Problem restatement + solution summary
   ├─ Why the edge is real (microstructure basis)
   ├─ Validation architecture (Phase 1-4 structure)
   ├─ Falsification criteria (when edge is dead)
   └─ Commitment to accepting failure
   
   → Read this THIRD for alignment and approval

4. DECISION_TREE_S8_VALIDATION.md (Phase-by-Phase)
   ├─ Phase 1: Backtest (Is edge real? ≥42% win rate needed)
   ├─ Phase 2: OOS test (Does it generalize? ≥39% needed)
   ├─ Phase 3: Paper trade (Is slippage valid? ≤1.5 pips needed)
   ├─ Phase 4: Live trade (Is strategy profitable? ≥1.0 Sharpe needed)
   ├─ Decision matrix (pass/fail criteria at each phase)
   └─ Emergency stop conditions (when to pause immediately)
   
   → Read this FOURTH for execution methodology

5. CHECKLIST_EDGE_FIRST_REFACTORING.md (Team Coordination)
   ├─ Documentation review checklist
   ├─ Conceptual alignment checklist (do we understand?)
   ├─ Technical requirements checklist
   ├─ Phase 1-4 checklists with metrics
   ├─ Failure root cause analysis template
   └─ Sign-off requirements before each phase
   
   → Use this FIFTH for team coordination and progress tracking
```

---

## QUICK START: READ ORDER

### For Project Manager / Stakeholder
1. Read: EDGE_FIRST_SUMMARY.md (5 min)
   - Understand problem and solution
2. Read: DECISION_TREE_S8_VALIDATION.md (10 min)
   - Understand timeline and decision points
3. Review: CHECKLIST_EDGE_FIRST_REFACTORING.md
   - Use for progress tracking

### For Development Lead
1. Read: EDGE_FIRST_RESEARCH.md (20 min)
   - Understand edge hypothesis
2. Read: S8_IMPLEMENTATION_BLUEPRINT.md (30 min)
   - Understand code structure and data flow
3. Use: CHECKLIST_EDGE_FIRST_REFACTORING.md
   - Technical requirements and Phase 1-2 execution

### For Trading Lead
1. Read: EDGE_FIRST_RESEARCH.md (20 min)
   - Understand edge hypothesis and why it works
2. Read: DECISION_TREE_S8_VALIDATION.md (20 min)
   - Understand Phase 3-4 (paper and live trading)
3. Use: CHECKLIST_EDGE_FIRST_REFACTORING.md
   - Phase 3-4 monitoring and emergency stops

### For Risk Officer
1. Read: EDGE_FIRST_SUMMARY.md (5 min)
   - Understand overall approach
2. Read: DECISION_TREE_S8_VALIDATION.md (Phase 4 section)
   - Understand DD limits and escalation procedures
3. Use: CHECKLIST_EDGE_FIRST_REFACTORING.md
   - Phase 4 monitoring checklist

---

## CORE MESSAGES (TL;DR)

### The Problem
Existing strategies (S1-S7) are **pattern-dependent**: they trade EMA crosses, ADX thresholds, regime labels. After costs, these patterns wash out (45-50% win rate = breakeven or negative).

### The Solution
Move to **edge-first design**: Find market conditions where risk/reward is **asymmetrically favorable** due to microstructure (not curve-fit).

### The Edge: Volatility Compression → Expansion
- **What happens**: Market enters low-volatility compression (natural clustering), then ATR breaks out
- **Why it works**: Forced liquidations + trend-followers create momentum in first 2-4 bars
- **Cost survival**: High-vol breakouts have better fills + lower effective spreads
- **Expected performance**: 42-50% win rate (3-5 pips moves vs 1-2 in compression)

### The Validation Process
1. **Phase 1 (Backtest)**: Prove edge exists (win rate ≥42% over 100+ events)
2. **Phase 2 (OOS)**: Prove edge generalizes (win rate ≥39% on held-out data)
3. **Phase 3 (Paper)**: Prove slippage model is valid (actual slip ≤1.5 pips)
4. **Phase 4 (Live)**: Prove strategy is profitable (monthly Sharpe ≥1.0)

### The Commitment
- **If any phase fails**: Accept defeat immediately. DO NOT force strategy live.
- **If all phases pass**: Strategy is ready for small-scale live trading with strict DD monitoring.
- **Parameters are frozen**: No re-optimization at any phase (prevents curve-fitting).

---

## WHAT'S DIFFERENT FROM S1-S7

| Aspect | S1-S7 (Pattern-Based) | S8 (Edge-First) |
|--------|----------------------|-----------------|
| **Entry Signal** | EMA cross, ADX threshold | Volatility breakout (objective percentile) |
| **Parameter Optimization** | Heavy (5-10 variables tuned) | None (fixed from Phase 1) |
| **Expected Win Rate** | 45-50% (breakeven) | 42-50% (profitable if real) |
| **Validation** | Backtest only (curve-fit risk) | 4 phases (backtest → OOS → paper → live) |
| **Trade Frequency** | 2-5/week (medium) | 1-2/week (low) |
| **Risk/Reward** | 1:1.5 typical | 1:2.5 (high) |
| **Failure Acceptance** | Deployed if backtest looks good | Stopped immediately if edge doesn't exist |

---

## KEY DIFFERENCES: WHY THIS WORKS

### 1. Structural Edge vs. Pattern
- **Pattern**: "When EMA fast > EMA slow, buy"
  - Works in backtest (was optimized for that data)
  - Fails live (pattern shifts as market changes)
- **Edge**: "When volatility compresses then expands, momentum persists 2-4 bars"
  - Based on documented market microstructure (Andersen et al., 1999)
  - Does NOT rely on specific indicator parameters
  - Works across asset classes (equities, bonds, FX)

### 2. Multi-Phase Validation vs. Single Backtest
- **Old**: Backtest looks good → Deploy live → Discover loses money
- **New**: Backtest ≥42% → OOS ≥39% → Paper ≤1.5pips slip → Live Sharpe ≥1.0 → Deploy

### 3. Frozen Parameters vs. Optimization
- **Old**: Best parameters found in backtest, deployed live
  - Parameters optimized for historical data
  - Likely degraded live (curve-fit)
- **New**: Parameters frozen from Phase 1, tested on Phase 2-4
  - No opportunity for curve-fit
  - If strategy fails OOS, we KNOW parameters don't work

### 4. Acceptance of Failure vs. Hope
- **Old**: If backtest loses money, tweak parameters and re-backtest (infinite loop)
- **New**: If Phase 1 shows win rate <40%, strategy is DEAD (move to next edge)

---

## SUCCESS METRICS BY PHASE

| Phase | Test | Success Metric | Failure Metric | If Success | If Failure |
|-------|------|----------------|----------------|------------|-----------|
| **1** | Backtest 5yr IS | Win% ≥42% | Win% <40% | → Phase 2 | → STOP |
| **2** | Backtest 1yr OOS | Win% ≥39% | Win% <35% | → Phase 3 | → STOP |
| **3** | Paper trade 2-4w | Slip ≤1.5p | Slip >2.0p | → Phase 4 | → STOP |
| **4** | Live trade 4-12w | Sharpe ≥1.0 | Sharpe <0.5 | → Scale ✓ | → STOP |

---

## TIMELINE ESTIMATE

- **Phase 0 (Research)**: ✅ COMPLETE (this package)
- **Phase 1 (Backtest)**: 1-2 days (dev + data science)
- **Phase 2 (OOS Test)**: 1 day (dev)
- **Phase 3 (Paper Trade)**: 2-4 weeks (trader)
- **Phase 4 (Live Trade)**: 4-12 weeks (trader + monitoring)

**Total**: ~6-8 weeks to either PROVE edge or ACCEPT failure

---

## NEXT STEPS (IMMEDIATE)

### Step 1: Review & Alignment (Today)
- [ ] Stakeholder reads: EDGE_FIRST_SUMMARY.md
- [ ] Dev reads: S8_IMPLEMENTATION_BLUEPRINT.md
- [ ] Trader reads: DECISION_TREE_S8_VALIDATION.md
- [ ] Team alignment meeting (30 min)

### Step 2: Phase 1 Planning (Tomorrow)
- [ ] Confirm EURUSD M15 data available (2020-2024)
- [ ] Confirm H4 data available (for ADX gating)
- [ ] Allocate dev resources (1-2 days)
- [ ] Schedule Phase 1 backtest execution

### Step 3: Phase 1 Execution (Days 3-5)
- [ ] Implement data functions (percentile rank, compression detection)
- [ ] Implement S8 strategy module
- [ ] Run 5-year backtest
- [ ] Extract win rate, Sharpe, profit factor

### Step 4: Go/No-Go Decision (Day 6)
- [ ] Analyze Phase 1 results
- [ ] Win rate ≥42%? → GREEN LIGHT (proceed to Phase 2)
- [ ] Win rate <40%? → RED LIGHT (edge is dead, stop)

---

## HOW TO USE THIS PACKAGE

### During Phase 1 (Backtest)
1. Reference: S8_IMPLEMENTATION_BLUEPRINT.md (code structure)
2. Reference: CHECKLIST_EDGE_FIRST_REFACTORING.md (Phase 1 section)
3. Target: Win rate ≥42%, profit factor ≥1.2

### During Phase 2 (OOS Test)
1. Reference: DECISION_TREE_S8_VALIDATION.md (Phase 2 section)
2. Reference: CHECKLIST_EDGE_FIRST_REFACTORING.md (Phase 2 section)
3. Target: Win rate ≥39%, Sharpe ≥0.5

### During Phase 3 (Paper Trade)
1. Reference: DECISION_TREE_S8_VALIDATION.md (Phase 3 section)
2. Reference: CHECKLIST_EDGE_FIRST_REFACTORING.md (Phase 3 section)
3. Target: Slippage ≤1.5 pips, win rate ≥40%

### During Phase 4 (Live Trade)
1. Reference: DECISION_TREE_S8_VALIDATION.md (Phase 4 section)
2. Reference: CHECKLIST_EDGE_FIRST_REFACTORING.md (emergency stops)
3. Target: Monthly Sharpe ≥1.0, DD ≤5% weekly

---

## CRITICAL ASSUMPTIONS

This entire research rests on **ONE assumption**:

> *Volatility-driven forced liquidations in the first 2-4 bars post-compression-breakout show **asymmetric risk/reward** that survives execution costs.*

**How to test**: Run Phase 1 backtest. If win rate ≥42% over 100+ events, assumption is TRUE.

**If assumption is FALSE** (win rate <40%): Accept failure, move to Condition 2 (Early Trend Ignition) or Condition 3 (Range Mean Reversion).

---

## INFRASTRUCTURE COMPATIBILITY

✅ **Preserved**:
- Existing strategies (S1-S7) unaffected
- Cost model (spread, slippage, spike) unchanged
- DD guard and position sizing rules active
- Regime engine and ADX calculations reused

✅ **Added**:
- ATR percentile rank function (simple, no optimization)
- Compression event detection function
- S8 strategy module (minimal, low frequency)
- Regression tests (ensure no breakage)

✅ **No Breaking Changes**:
- Can enable/disable S8 via config
- Existing backtests still run on S1-S7
- No modification to bar contract or execution model

---

## APPROVAL GATE

**This package is approved for Phase 1 implementation if:**

- [x] Edge hypothesis is clear and falsifiable
- [x] 3 alternative edges were researched
- [x] Validation process is rigorous (4 phases, clear metrics)
- [x] Team understands: Edge can FAIL
- [x] Team commits to: Accept failure if Phase 1 shows win% <40%
- [x] Infrastructure preserved: No breaking changes
- [x] Data available: 5+ years clean EURUSD M15/H4
- [x] Success metrics defined and frozen

**Approval Required From**:
- [ ] Project Stakeholder
- [ ] Development Lead
- [ ] Trading Lead
- [ ] Risk Officer

---

## RESOURCES

### Data Science / Development
- Phase 1-2: ~3-4 days effort
- Required: Python, pandas, numpy (existing)
- References: S8_IMPLEMENTATION_BLUEPRINT.md

### Trading
- Phase 3-4: ~6-16 weeks (paper + live)
- Required: Discipline, daily monitoring
- References: DECISION_TREE_S8_VALIDATION.md

### Risk / Monitoring
- Phase 4 ongoing: Weekly monitoring, escalation procedures
- References: CHECKLIST_EDGE_FIRST_REFACTORING.md (Phase 4 section)

---

## WHAT SUCCESS LOOKS LIKE

**Phase 1 Backtest**:
- 120 compression → expansion events identified
- Win rate: 44% (exceeds 42% threshold)
- Profit factor: 1.25 (exceeds 1.2 threshold)
- Sharpe: 0.95 (exceeds 0.8 threshold)
- Result: PROCEED TO PHASE 2 ✓

**Phase 2 OOS Test**:
- 28 events in OOS 2024-2025 data
- Win rate: 41% (within 3% of Phase 1)
- Sharpe: 0.68 (within acceptable range)
- Result: PROCEED TO PHASE 3 ✓

**Phase 3 Paper Trading**:
- 12 trades over 3 weeks
- Actual entry slippage: 1.2 pips (vs model 1.0)
- Actual exit slippage: 1.1 pips (vs model 1.0)
- Win rate: 42% (matches Phase 2)
- Result: PROCEED TO PHASE 4 ✓

**Phase 4 Live Trading**:
- 8 trades in first month
- Monthly return: +1.2% (positive)
- Monthly Sharpe: 1.15 (exceeds 1.0)
- Max DD: 3.2% (within 5% limit)
- Result: STRATEGY APPROVED, SCALE GRADUALLY ✓

---

## WHAT FAILURE LOOKS LIKE

**Phase 1 Backtest FAILS**:
- 89 events identified (below 100 target)
- Win rate: 38% (below 42% threshold)
- Result: STOP. Edge does not exist.

**Phase 2 OOS Test FAILS**:
- Win rate OOS: 32% (8% degradation from Phase 1 45%)
- Result: STOP. Curve-fit detected.

**Phase 3 Paper Trading FAILS**:
- Actual entry slippage: 2.8 pips (vs model 1.0)
- Result: STOP. Slippage model broken.

**Phase 4 Live Trading FAILS**:
- Month 1 return: -0.8%
- Month 2 return: -1.2%
- Result: STOP. Strategy not profitable live.

---

## FINAL CHECKLIST BEFORE STARTING

- [ ] All 5 documents reviewed by core team
- [ ] Edge hypothesis understood and approved
- [ ] Success/failure criteria agreed and documented
- [ ] Data confirmed available (EURUSD M15/H4, 5+ years)
- [ ] Development resources allocated (2-3 days Phase 1)
- [ ] Trading resources allocated (2-4 weeks Phase 3)
- [ ] Risk monitoring procedures defined (Phase 4)
- [ ] Emergency stop procedures documented

---

**Status**: READY FOR PHASE 1  
**Owner**: Development team (Phase 1-2), Trading team (Phase 3-4)  
**Timeline**: 1-2 weeks Phase 1, then 4-6 weeks total (if all phases pass)  

**Let's prove this edge exists, or accept it's dead.**

---

*Document Created: February 1, 2026*  
*Version: 1.0*  
*Classification: Internal Research*
