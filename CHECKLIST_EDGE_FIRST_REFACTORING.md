# EDGE-FIRST REFACTORING: TEAM CHECKLIST

Use this checklist to ensure all documentation is complete and understood before proceeding.

---

## DOCUMENTATION REVIEW CHECKLIST

### ✅ Phase 0: Research & Documentation (COMPLETE)

**Created Documents**:
- [x] `EDGE_FIRST_RESEARCH.md` (Main hypothesis, 3 candidate edges, S8 specification)
- [x] `S8_IMPLEMENTATION_BLUEPRINT.md` (Technical blueprint, data flow, code structure)
- [x] `EDGE_FIRST_SUMMARY.md` (Executive summary, validation architecture)
- [x] `DECISION_TREE_S8_VALIDATION.md` (Phase 1-4 decision tree, metrics)
- [x] `CHECKLIST_EDGE_FIRST_REFACTORING.md` (This document)

**Read & Understood By**:
- [ ] Project Manager: ________ (date)
- [ ] Lead Developer: ________ (date)
- [ ] Lead Trader: ________ (date)
- [ ] Risk Officer: ________ (date)

---

## CONCEPTUAL ALIGNMENT CHECKLIST

### Understand the Problem
- [ ] Current strategies (S1-S7) are pattern-dependent and mostly lose money after costs
- [ ] Root cause: Patterns discovered offline don't persist live
- [ ] Solution: Find structural market edges instead of patterns

### Understand S8 Edge Hypothesis
- [ ] Volatility clustering is documented fact (edge is NOT made up)
- [ ] Compression → expansion shows forced liquidation + momentum (edge is REAL)
- [ ] Edge can fail if: (a) compression not followed by expansion, (b) win rate actually <40%, (c) slippage too high
- [ ] Edge succeeds if: win rate ≥42% in backtest, ≥39% OOS, actual slippage ≤1.5 pips

### Understand the Validation Process
- [ ] Phase 1 (Backtest): Prove edge exists (win rate ≥42%)
- [ ] Phase 2 (OOS): Prove edge generalizes (win rate ≥39%)
- [ ] Phase 3 (Paper): Prove slippage model is valid
- [ ] Phase 4 (Live): Prove strategy is profitable with real capital
- [ ] NO parameter optimization at any phase (frozen from Phase 1)
- [ ] FAILURE AT ANY PHASE: Stop and accept defeat; do NOT force strategy live

### Understand the Constraints
- [ ] No new indicators (use existing ATR, ADX, regime)
- [ ] No changes to cost model or bar contract
- [ ] No increase in trade frequency (low volume by design)
- [ ] No overfitting or parameter grids (single set of fixed parameters)
- [ ] All existing infrastructure preserved (S1-S7 unaffected)

---

## TECHNICAL REQUIREMENTS CHECKLIST

### Data Requirements
- [ ] 5+ years EURUSD M15 data (2020-2024)
- [ ] 5+ years EURUSD H4 data (2020-2024, for ADX gating)
- [ ] Clean OHLC bars (no gaps, validated for lookahead issues)
- [ ] 1+ year held-out 2024-2025 data (for Phase 2 OOS test)

### Infrastructure Requirements
- [ ] Existing backtest system verified working (no lookahead, cost model correct)
- [ ] DD guard functional (position sizing, drawdown enforcement)
- [ ] Regime engine functional (WHIPSAW detection)
- [ ] H4 merge infrastructure tested (H4 → M15 without lookahead)
- [ ] Cost model validated (spread, slippage, spike model)

### Code Quality Requirements
- [ ] S8 strategy module has clear anti-lookahead design
- [ ] No copy-paste from S1-S7 (new logic, not modified old logic)
- [ ] All functions have docstrings explaining anti-lookahead
- [ ] Regression tests cover all gates and edge cases
- [ ] Code passes lint/format checks

---

## PHASE 1 BACKTEST CHECKLIST

### Pre-Backtest
- [ ] Data loaded and validated (no lookahead, no gaps)
- [ ] S8 strategy module complete and tested
- [ ] Orchestrator integration complete
- [ ] Regression tests all passing
- [ ] Parameters frozen (no optimization allowed)

### During Backtest
- [ ] Backtest runs without errors
- [ ] Compression → expansion events identified
- [ ] Total events: ≥100 (sufficient sample size)
- [ ] Execution timestamps recorded (for MAE analysis)
- [ ] Trade details exported (entry price, exit price, slippage model)

### Post-Backtest Analysis
- [ ] Win rate calculated: ______% (target: ≥42%)
- [ ] Profit factor calculated: _______ (target: ≥1.2)
- [ ] Average win: _______ pips (target: ≥18)
- [ ] Average loss: _______ pips (target: ≤12)
- [ ] Max drawdown: ______% (target: ≤8%)
- [ ] Sharpe ratio: _______ (target: ≥0.8)

### Decision Checkpoint Phase 1
```
ALL metrics PASS (win rate ≥42%, profit factor ≥1.2, DD ≤8%)?
    YES → Proceed to Phase 2 ✓
    NO → EDGE DEAD, stop and document failure
```

---

## PHASE 2 OUT-OF-SAMPLE CHECKLIST

### Pre-OOS Test
- [ ] Parameters frozen from Phase 1 (document exact values)
- [ ] Held-out 2024-2025 data loaded
- [ ] OOS backtest setup confirmed (same rules as Phase 1)

### During OOS Test
- [ ] OOS backtest runs without errors
- [ ] Compression → expansion events identified in OOS data
- [ ] Total events in OOS: ≥20 (sufficient for validation)

### Post-OOS Analysis
- [ ] Win rate calculated: ______% (target: ≥39%, within 3% of Phase 1)
- [ ] Profit factor calculated: _______ (target: ≥1.1)
- [ ] Sharpe ratio: _______ (target: ≥0.5)
- [ ] Average P&L per trade: _______ pips (target: >0 expected value)
- [ ] Comparison to Phase 1: Win rate degradation ______% (target: <5%)

### Decision Checkpoint Phase 2
```
OOS win rate ≥39% AND Sharpe ≥0.5 AND degradation <5%?
    YES → Edge generalizes, proceed to Phase 3 ✓
    MARGINAL (35-39% win rate) → Results unclear, DO NOT proceed
    NO → Curve-fit detected, STOP
```

---

## PHASE 3 PAPER TRADING CHECKLIST

### Pre-Paper Trading
- [ ] Parameters frozen from Phase 1 (same exact values)
- [ ] Paper trading account configured (no real capital risk)
- [ ] Real-time market data feed validated
- [ ] Trade logging system ready (record slippage per trade)

### During Paper Trading (2-4 weeks)
- [ ] Trading daily with S8 strategy
- [ ] Recording per-trade: entry slip, exit slip, MAE, exit price
- [ ] Monitoring daily: win rate, cumulative P&L, drawdown
- [ ] Weekly review: Compare to backtest expectations

### Post-Paper Trading Analysis
- [ ] Total trades executed: _______ (target: ≥10)
- [ ] Avg entry slippage: _______ pips (target: ≤1.5, vs backtest 1.0)
- [ ] Avg exit slippage: _______ pips (target: ≤1.5, vs backtest 1.0)
- [ ] Avg MAE: _______ pips (target: ≤5)
- [ ] Win rate achieved: ______% (target: ≥40%, close to OOS 39%)
- [ ] Weekly max DD: ______% (target: consistent with backtest)

### Slippage Model Validation
```
Actual avg slippage ≤1.5 pips AND win rate ≥40%?
    YES → Slippage model valid, proceed to Phase 4 ✓
    MARGINAL (1.5-2.0 pips slip) → Reduce position size 20%, retry
    NO → Slippage model broken, STOP
```

---

## PHASE 4 LIVE TRADING CHECKLIST

### Pre-Live Trading
- [ ] Parameters frozen from Phase 1 (verified exact match)
- [ ] Position sizing configured: 1% per trade
- [ ] DD limits enforced: 5% weekly, 8% monthly cap
- [ ] Trade logging system ready
- [ ] Escalation procedure documented (see Decision Tree)

### Weekly Monitoring
- [ ] Trades executed: _______ count (normal range)
- [ ] Win rate: ______% (target: ≥39%)
- [ ] Weekly P&L: _______ pips / ______%
- [ ] Weekly max DD: ______% (target: ≤5%)
- [ ] Avg trade duration: _______ bars (should be 2-4 for compression edge)
- [ ] Any red flags? (spread widening, slippage increase, etc.)

### Monthly Review (Decision Point)
```
Monthly Sharpe ≥1.0 AND monthly return >0% AND max DD ≤5%?
    YES → Strategy is profitable, continue monitoring ✓
    MARGINAL → Results unclear, collect more data
    NO → STOP strategy, escalate failure investigation
```

### Emergency Stop Conditions (Trigger Immediately)
- [ ] 3 consecutive losing days → PAUSE 1 week
- [ ] Any week with >5% DD → PAUSE 2 weeks
- [ ] Spread widens >5 pips → PAUSE, investigate
- [ ] Any month with <30% win rate → ESCALATE to research team

---

## FAILURE ROOT CAUSE ANALYSIS

**If Phase 1 FAILS (win rate <40%)**:
- [ ] Document: compression events found? (Y/N)
- [ ] Document: typical move size post-expansion (_______ pips)
- [ ] Document: win rate on long vs short (____% vs ____%)
- [ ] Conclusion: Edge hypothesis was wrong; move to Condition 2 or 3

**If Phase 2 FAILS (OOS win rate <35%)**:
- [ ] Document: parameters that were frozen
- [ ] Document: did OOS market conditions differ from IS? (Y/N)
- [ ] Conclusion: Curve-fit to Phase 1 data; parameters need revision

**If Phase 3 FAILS (actual slippage >2.0 pips)**:
- [ ] Document: which broker/feed used (slippage varies by venue)
- [ ] Document: typical spread observed (_______ pips)
- [ ] Conclusion: Slippage model too optimistic; adjust spread assumptions

**If Phase 4 FAILS (monthly Sharpe <0.5)**:
- [ ] Document: winning trades analysis (why won some, lost others)
- [ ] Document: regime/market conditions during failure period
- [ ] Document: did strategy comply with DD limits? (Y/N)
- [ ] Conclusion: Market regime changed; edge no longer valid in current conditions

---

## SIGN-OFF CHECKLIST

**Before Phase 1 Implementation**:
- [ ] All documentation reviewed and understood by core team
- [ ] Edge hypothesis approved (edge is valid or will be proven false)
- [ ] Data sources confirmed available
- [ ] Development resources allocated (2-3 days for Phase 1)

**Before Phase 2 Execution**:
- [ ] Phase 1 PASSED (win rate ≥42%)
- [ ] Parameters officially frozen (documented in version control)
- [ ] Phase 2 resources allocated (1 day for OOS test)

**Before Phase 3 Execution**:
- [ ] Phase 2 PASSED (win rate ≥39%)
- [ ] Paper trading infrastructure ready
- [ ] Phase 3 resources allocated (2-4 weeks, 1 trader)

**Before Phase 4 Execution**:
- [ ] Phase 3 PASSED (slippage ≤1.5 pips, win rate ≥40%)
- [ ] Live account configured with position sizing
- [ ] DD limits enforced in broker/risk system
- [ ] Phase 4 resources allocated (4-12 weeks, ongoing monitoring)

---

## FINAL APPROVAL

**This research is ready to proceed if ALL of the following are true:**

- [x] Edge hypothesis is documented and falsifiable
- [x] 3 alternative edges researched and ranked
- [x] S8 strategy module architecture is designed
- [x] Validation process is rigorous (backtest → OOS → paper → live)
- [x] Team understands: Edge can FAIL at any phase
- [x] Team commits to: If edge fails, strategy does NOT go live
- [x] Infrastructure preserved: No breaking changes to existing system
- [x] Data available: 5+ years EURUSD M15 + H4 clean data
- [x] Success metrics defined: Win rate ≥42% (Phase 1), ≥39% (Phase 2), etc.

**Approval Authority**: _______________ (print name, sign, date)

**Development Lead**: _______________ (print name, sign, date)

**Trading Lead**: _______________ (print name, sign, date)

---

**Status**: READY FOR PHASE 1 IMPLEMENTATION

**Timeline**: 1-2 weeks Phase 1, then 4-6 weeks to Phase 4 completion (if all phases pass)

**Owner**: Development team (Phase 1-2), Trading team (Phase 3-4), Risk team (monitoring)

---

**Document Version**: 1.0  
**Date**: 2026-02-01  
**Last Updated**: 2026-02-01
