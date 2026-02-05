# DECISION TREE: S8 VALIDATION FLOW

This document maps the validation journey for S8_VOL_COMPRESSION_EXPANSION strategy.

---

## DECISION FLOW

```
START: Edge Hypothesis
  ↓
Do we have EURUSD M15 + H4 data (5+ years)?
  ├─ NO → Source data, try again
  └─ YES ↓
  
PHASE 1: BACKTEST (5 years historical data)
  Run S8 with frozen parameters
  Extract: win rate, avg P&L, Sharpe, max DD
  ↓
  Is win rate >= 42% AND profit factor >= 1.2 AND max DD <= 8%?
  ├─ NO (win rate < 40%) → EDGE DEAD. Stop. Document failure.
  ├─ MAYBE (win rate 40-42%) → Increase sample size (backtest 10 years if available)
  └─ YES (win rate >= 42%) ↓
  
PHASE 2: OUT-OF-SAMPLE TEST (2024-2025 held-out data)
  Apply S8 with parameters frozen from Phase 1
  Extract: win rate, avg P&L, Sharpe
  ↓
  Is OOS win rate >= 39% (within 3% of IS)?
  ├─ NO (win rate < 35%) → CURVE-FIT DETECTED. Stop. Revisit parameters.
  ├─ MARGINAL (win rate 35-39%) → Results unclear. Do NOT proceed to live.
  └─ YES (win rate >= 39%) ↓
  
PHASE 3: PAPER TRADING (2-4 weeks with real-time data)
  Trade S8 on paper account
  Validate: entry slippage, exit slippage, actual win rate
  ↓
  Is actual slippage <= 1.5 pips AND win rate >= 38%?
  ├─ NO (slippage > 2 pips OR win rate < 35%) → SLIPPAGE MODEL BROKEN. Stop.
  └─ YES (slippage valid, win rate ~= OOS) ↓
  
PHASE 4: LIVE TRADING (4-12 weeks with real capital)
  Trade S8 with 1% position sizing per trade
  Monitor: daily/weekly returns, DD, win rate
  ↓
  Is monthly Sharpe >= 1.0 AND max DD <= 5% AND win rate >= 39%?
  ├─ NO (negative return OR DD > 5%) → STOP STRATEGY. Investigate failure.
  └─ YES (profitable, controlled DD) → STRATEGY APPROVED. Scale gradually.
  
  Ongoing Monitoring:
  ├─ 3 consecutive losing days? → Pause 1 week, review
  ├─ Week with >5% DD? → Pause 2 weeks, investigate
  ├─ Month with <30% win rate? → Escalate to research team
  └─ Strategy performing >= 1.0 Sharpe? → Continue monitoring, scale if desired
```

---

## PHASE 1: BACKTEST ANALYSIS

**Question**: Does the edge exist in historical data?

### Inputs
- 5 years EURUSD M15 data (2020-2024)
- Fixed parameters:
  - Compression threshold: ATR percentile < 20
  - Min duration: 10 bars
  - Expansion trigger: ATR percentile >= 30
  - SL: 10 pips, TP: 25 pips
  - ADX gates: 20-50
  - Regime gate: NOT WHIPSAW

### Outputs
- Total compression→expansion events identified (target: 100+)
- Win rate (%)
- Average win (pips)
- Average loss (pips)
- Profit factor (total_wins / total_losses)
- Max drawdown (%)
- Sharpe ratio
- Trade duration (avg bars)

### Pass/Fail Criteria

| Metric | Pass | Fail |
|--------|------|------|
| **Events** | ≥100 | <50 (insufficient sample) |
| **Win Rate** | ≥42% | <40% |
| **Avg Win** | ≥18 | <15 |
| **Avg Loss** | ≤12 | >15 |
| **Profit Factor** | ≥1.2 | <1.0 |
| **Max DD** | ≤8% | >10% |
| **Sharpe** | ≥0.8 | <0.5 |

**Decision**:
- **ALL metrics PASS** → Proceed to Phase 2
- **ANY metric FAILS** → EDGE DEAD, stop
- **2-3 metrics marginal** → Increase sample size (backtest 10 years if possible)

---

## PHASE 2: OUT-OF-SAMPLE TEST

**Question**: Does the edge generalize to data not used for design?

### Inputs
- 1 year EURUSD M15 data (2024-2025, held-out)
- S8 parameters frozen from Phase 1 (NO re-optimization)

### Outputs
- Total compression→expansion events on OOS data
- Win rate (%)
- Average win (pips)
- Average loss (pips)
- Profit factor
- Max drawdown (%)
- Sharpe ratio

### Pass/Fail Criteria

| Comparison | Pass | Fail |
|------------|------|------|
| **OOS Win Rate** | ≥39% (within -3% of IS) | <35% (>7% degradation) |
| **OOS Sharpe** | ≥0.5 | <0.0 |
| **OOS Profit Factor** | ≥1.1 | <0.95 (losing money) |
| **Sample Size** | ≥20 events | <10 (insufficient) |

**Decision**:
- **OOS win rate ≥39% AND Sharpe ≥0.5** → Edge generalizes, proceed to Phase 3
- **OOS win rate <35% OR Sharpe <0.0** → Curve-fit detected, STOP
- **Marginal (35-39% win rate)** → Results unclear, DO NOT proceed to Phase 4

### What Degradation Is Acceptable?

- IS win rate 42% → OOS 39% is OK (3% margin)
- IS win rate 42% → OOS 35% is NOT OK (7% = curve-fit)
- IS win rate 50% → OOS 45% is OK (5% margin)
- IS win rate 50% → OOS 40% is NOT OK (10% = too much decay)

---

## PHASE 3: PAPER TRADING

**Question**: Does the slippage model match reality?

### Inputs
- 2-4 weeks real-time EURUSD M15 data
- Paper trading account (no real capital risk)
- Same S8 strategy logic as Phase 1-2

### Outputs (per trade)
- Entry price (bid/ask at execution)
- Entry slippage (vs. expected fill)
- Exit price (bid/ask at exit)
- Exit slippage (vs. expected TP/SL)
- Actual max adverse excursion (MAE)
- Actual P&L per trade

### Aggregate Outputs
- Average entry slippage (pips)
- Average exit slippage (pips)
- Average MAE (pips)
- Overall win rate (%)
- Sharpe ratio

### Pass/Fail Criteria

| Metric | Backtest | Paper | Acceptable Diff | Pass/Fail |
|--------|----------|-------|-----------------|-----------|
| **Avg Entry Slip** | 1.0 pips | ? | ±0.5 pips | If ≤1.5 → PASS |
| **Avg Exit Slip** | 1.0 pips | ? | ±0.5 pips | If ≤1.5 → PASS |
| **Avg MAE** | 3-4 pips | ? | ±1 pip | If ≤5 pips → PASS |
| **Win Rate** | 42% | ? | ±2% | If ≥40% → PASS |

**Decision**:
- **Actual slippage ≤1.5 pips AND win rate ≥40%** → Proceed to Phase 4 (live)
- **Actual slippage >2.0 pips OR win rate <35%** → SLIPPAGE MODEL BROKEN, STOP
- **Marginal slippage (1.5-2.0 pips)** → Reduce position size 20%, retry Phase 3

---

## PHASE 4: LIVE TRADING

**Question**: Is the strategy profitable with real capital?

### Inputs
- Real capital (prop firm or personal account)
- 1% position sizing per trade
- Monthly/weekly monitoring
- Prop firm DD limits enforced

### Monitoring Outputs (Weekly)
- Trades taken (count)
- Win rate (%)
- Weekly P&L (pips / %)
- Weekly max DD (%)
- Avg trade duration

### Monitoring Outputs (Monthly)
- Trades taken (count)
- Win rate (%)
- Monthly P&L (%)
- Monthly Sharpe ratio
- Monthly max DD (%)
- Compliance: DD rule breaches, position violations

### Pass/Fail Criteria (Monthly)

| Metric | Pass | Fail | Action |
|--------|------|------|--------|
| **Win Rate** | ≥39% | <30% | Escalate to research |
| **Monthly Sharpe** | ≥1.0 | <0.5 | Pause strategy 2 weeks |
| **Monthly Return** | >0% | <-2% | Pause strategy 2 weeks |
| **Max DD** | ≤5% | >5% | Pause strategy 2 weeks |

### Emergency Stop Conditions

**PAUSE strategy immediately if**:
1. 3 consecutive losing days
2. Any single week with >5% DD
3. Spread widens abnormally (>5 pips on EURUSD)
4. More than 2 trades NOT triggered when signal present (execution failure)

### Escalation Path

- **1 PAUSE** (1 week) → Review data, check for regime change
- **2 PAUSES** (within 4 weeks) → Escalate to research team, consider strategy modification
- **3 PAUSES** (within 8 weeks) → Strategy likely dead, prepare to stop live trading
- **Any month with Sharpe <0.5** → Immediate escalation

### Success Metrics

**If strategy achieves for 4+ weeks**:
- Monthly Sharpe ≥1.0
- Win rate ≥39%
- Monthly return >1%
- Max DD ≤5% weekly

**Then**: Strategy is viable, can increase position sizing or scale gradually.

---

## QUICK REFERENCE: Decision Matrix

```
                  PHASE 1            PHASE 2              PHASE 3            PHASE 4
                  BACKTEST           OUT-OF-SAMPLE        PAPER TRADE        LIVE
                  ========           ==============        ===========        ====
Input Data:       5yr IS data        1yr OOS data         Real-time (2-4w)    Real capital
Parameter Lock:   Frozen             Frozen               Frozen              Frozen
Risk Level:       None (backtest)    None (backtest)      Minimal (paper)     Real ($)

Key Metric:       Win Rate ≥42%      Win Rate ≥39%        Win Rate ≥40%       Sharpe ≥1.0
                  Profit Factor ≥1.2 Sharpe ≥0.5          Slippage ≤1.5pips   DD ≤5%

Pass Decision:    EDGE EXISTS        EDGE GENERALIZES     SLIPPAGE VALID      STRATEGY LIVE
Fail Decision:    EDGE DEAD          CURVE-FIT            MODEL BROKEN        STOP LIVE

Duration:         1-2 days           4 hours              2-4 weeks           4-12 weeks

Next Action:      If PASS → Ph2      If PASS → Ph3        If PASS → Ph4       Monitor
                  If FAIL → STOP     If FAIL → STOP       If FAIL → STOP      If FAIL → STOP
```

---

## TIMELINE TEMPLATE

### Week 1-2: Phase 1 (Backtest)
- Day 1-2: Prepare data, implement S8 strategy module
- Day 3-5: Run 5-year backtest, extract compression events
- Day 6-7: Analyze results, document findings

**Decision Point**: Phase 1 PASS/FAIL

### Week 3: Phase 2 (Out-of-Sample)
- Day 1-2: Extract 2024-2025 held-out data
- Day 3: Run OOS backtest with frozen parameters
- Day 4: Analyze, compare to Phase 1

**Decision Point**: Phase 2 PASS/FAIL

### Week 4-7: Phase 3 (Paper Trading)
- Day 1: Start paper trading with real-time data
- Days 2-28: Monitor slippage, win rate, MAE
- Day 29: Analyze paper trading results, decide Phase 4

**Decision Point**: Phase 3 PASS/FAIL

### Week 8-19: Phase 4 (Live Trading)
- Week 1-2: Live trade with 1% position sizing, weekly monitoring
- Week 3-4: Monthly performance check, decision on scale/pause/stop
- Week 5-12: Ongoing monitoring, escalation if needed

**Decision Point**: Monthly Sharpe ≥1.0, DD ≤5% (continue) or FAIL (stop)

---

## HOW TO USE THIS DOCUMENT

**For Project Manager**:
- Use the flow chart to track progress
- Check decision criteria at each phase
- If any phase fails, document failure reason

**For Data Scientist**:
- Execute Phase 1-2 backtest
- Report: win rate, Sharpe, profit factor, failures
- Freeze parameters before Phase 3

**For Trader**:
- Execute Phase 3 paper trading
- Record: actual entry/exit slippage per trade
- Validate slippage model matches backtest assumptions
- If approved, execute Phase 4 live trading

**For Risk Officer**:
- Monitor Phase 4 live trading
- Enforce DD limits, position sizing rules
- Escalate if any pause condition triggered

---

**Document Version**: 1.0  
**Last Updated**: 2026-02-01  
**Status**: READY FOR IMPLEMENTATION
