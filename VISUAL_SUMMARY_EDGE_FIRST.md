# EDGE-FIRST REFACTORING: ONE-PAGE VISUAL SUMMARY

---

## THE PROBLEM

```
Current System (S1-S7)
═════════════════════

Offline Analysis          Live Trading              Result
    ↓                         ↓                        ↓
"Find pattern"    →    Backtest looks good    →    Loses money
"Optimize it"     →    Deploy live with hope  →    (costs kill edge)
"Deploy live"     →    Win rate drops to 45%  →    Curve-fit detected


Root Cause: Patterns are discovered offline, then deployed live.
           Parameters optimized for historical data, don't persist.
           
Result: Most strategies cluster at ~50% win rate (breakeven or worse after costs).
```

---

## THE SOLUTION: EDGE-FIRST DESIGN

```
New System (S8 + Future Edges)
══════════════════════════════

Find Structural       Validate Rigorously      Deploy with Confidence
    ↓                        ↓                        ↓
Volatility clustering  → Phase 1: Backtest    → Strategy works
+ forced liquidation       (win% ≥42?)        (win% stays ≥39%)
                       → Phase 2: OOS test    
                           (win% ≥39?)        
                       → Phase 3: Paper trade 
                           (slip ≤1.5p?)      
                       → Phase 4: Live trade  
                           (Sharpe ≥1.0?)     


Commitment: If ANYTHING fails in Phase 1-4, strategy is DEAD. No exceptions.
            Parameters frozen from Phase 1 (prevents curve-fit).
            Only proceed to next phase if criteria met.
```

---

## S8: VOLATILITY BREAKOUT STRATEGY

### The Edge

```
Market Dynamics:

Low-Vol Period              Breakout Event              High-Vol Regime
  ├─ ATR compressed         ├─ ATR breaks out           ├─ Forced liquidations
  ├─ Participants de-risk   ├─ Trend followers enter   ├─ Momentum continues
  └─ Thin orderbook         └─ Forced stops triggered   └─ 2-4 bar trend

WHY IT WORKS:
• Volatility clustering is documented (Andersen et al., 1999)
• Forced liquidations create directional momentum
• Cost advantage in high-vol (tighter spreads, better R:R)
• Window is SHORT (2-4 bars) before mean-reversion bots kick in

EDGE FAILS IF:
• Compression not followed by expansion (false signal)
• Immediate reversal (false breakout)
• Win rate actually <40% (edge is illusion)
• Slippage too high in real trading (model is wrong)
```

### Entry/Exit Logic

```
Entry Trigger:                Exit Rules:
├─ ATR percentile < 20         ├─ HARD SL: 10 pips fixed
│  for 10+ bars                │  (accept 1-2 bar whipsaws)
├─ ATR breaks > 30             │
│  (single bar)                ├─ Initial TP: 25 pips
├─ Direction: Close > Open     │  (captures typical 4-8 pip move)
│  (LONG) or Close < Open      │
│  (SHORT)                     ├─ Trailing: H1 Chandelier
│                              │  (trail up after 3 pips profit)
├─ Gating: ADX 20-50           │
│  (structure, not over-ext)   └─ Timeout: 4 hours max
│                              (prevents overnight hold)
├─ Gating: Regime ≠ WHIPSAW    
│  (avoid choppy markets)      
│                              
└─ Gating: No >10p gaps        
   (overnight stability)       

Result: Low frequency (1-2/week), high quality (1:2.5 R:R), clear SL.
```

---

## VALIDATION ARCHITECTURE

```
4-PHASE VALIDATION PROCESS
═══════════════════════════

PHASE 1: BACKTEST         PHASE 2: OUT-OF-SAMPLE   PHASE 3: PAPER TRADE   PHASE 4: LIVE TRADE
(Prove Edge Exists)       (Prove It Generalizes)  (Prove Slippage Valid) (Prove Profitable)
│                         │                        │                      │
Input: 5yr IS data        Input: 1yr OOS data     Input: Real-time, 2-4w Input: Real capital
       EURUSD M15         (2024-2025, held-out)   Paper account          (1% pos sizing)
       2020-2024                                  
│                         │                        │                      │
Run: S8 backtest          Run: S8 backtest        Run: S8 trading        Run: S8 trading
     (no optimization)         (PARAMS FROZEN)    (PARAMS FROZEN)        (PARAMS FROZEN)
│                         │                        │                      │
Measure:                  Measure:                Measure:               Measure:
├─ Win% ≥42%             ├─ Win% ≥39%            ├─ Entry slip ≤1.5p   ├─ Sharpe ≥1.0
├─ Profit factor ≥1.2    ├─ Sharpe ≥0.5          ├─ Exit slip ≤1.5p    ├─ Monthly ret >0%
├─ Max DD ≤8%            ├─ Profit factor ≥1.1   ├─ Win% ≥40%          ├─ Max DD ≤5%/week
└─ Sharpe ≥0.8           └─ Sufficient events (≥20) └─ Sufficient trades (≥10) └─ Compliance OK
│                         │                        │                      │
PASS                      PASS                    PASS                   PASS
 ↓                         ↓                        ↓                       ↓
→ Phase 2            → Phase 3               → Phase 4               → STRATEGY
  (edge exists)         (generalizes)         (slippage valid)         APPROVED ✓

FAIL                      FAIL                    FAIL                   FAIL
 ↓                         ↓                        ↓                       ↓
STOP                   STOP                    STOP                   STOP
(edge dead)            (curve-fit)             (model broken)         (not profitable)
```

---

## QUICK METRICS

### Phase 1: Backtest (5 years EURUSD)
```
Success Target:                Current:           Status:
├─ Win rate ≥42%              ?                 [PENDING PHASE 1]
├─ Profit factor ≥1.2         ?                 [PENDING PHASE 1]
├─ Max DD ≤8%                 ?                 [PENDING PHASE 1]
├─ Sharpe ≥0.8                ?                 [PENDING PHASE 1]
└─ Events ≥100                ?                 [PENDING PHASE 1]

Timeline: 1-2 days (backtest + analysis)
Decision: Win% ≥42% → PASS (proceed Phase 2)
          Win% <40% → FAIL (edge dead)
```

### Phase 2: Out-of-Sample (2024-2025)
```
Success Target:                Current:           Status:
├─ Win rate ≥39%              ?                 [PENDING PHASE 1]
├─ Sharpe ≥0.5                ?                 [PENDING PHASE 1]
├─ Degradation <5%            ?                 [PENDING PHASE 1]
└─ Events ≥20                 ?                 [PENDING PHASE 1]

Timeline: 4 hours (after Phase 1 completes)
Decision: Win% ≥39% AND Sharpe ≥0.5 → PASS (proceed Phase 3)
          Win% <35% → FAIL (curve-fit)
```

### Phase 3: Paper Trading (2-4 weeks)
```
Success Target:                Current:           Status:
├─ Entry slip ≤1.5p           ?                 [PENDING PHASE 2]
├─ Exit slip ≤1.5p            ?                 [PENDING PHASE 2]
├─ Win rate ≥40%              ?                 [PENDING PHASE 2]
└─ Trades ≥10                 ?                 [PENDING PHASE 2]

Timeline: 2-4 weeks (trader monitoring)
Decision: Slip ≤1.5p AND Win% ≥40% → PASS (proceed Phase 4)
          Slip >2.0p → FAIL (model broken)
```

### Phase 4: Live Trading (4-12 weeks)
```
Success Target:                Current:           Status:
├─ Monthly Sharpe ≥1.0        ?                 [PENDING PHASE 3]
├─ Monthly return >0%          ?                 [PENDING PHASE 3]
├─ Max DD ≤5% weekly           ?                 [PENDING PHASE 3]
└─ Compliance OK               ?                 [PENDING PHASE 3]

Timeline: 4-12 weeks (ongoing monitoring)
Decision: Sharpe ≥1.0 AND DD ≤5% → APPROVED (continue with monitoring)
          Sharpe <0.5 → STOP (not profitable)
```

---

## TEAM RESPONSIBILITIES

```
Development Team (Phase 1-2)
  ├─ Implement: compute_atr_percentile_rank()
  ├─ Implement: detect_compression_events()
  ├─ Implement: S8 strategy module
  ├─ Register: S8 in STRATEGY_MAP
  ├─ Run: Phase 1 backtest (5 years)
  ├─ Analyze: Win rate, Sharpe, P&L
  ├─ Report: PASS/FAIL with metrics
  └─ Timeline: 1-2 days (Phase 1), 1 day (Phase 2)

Trading Team (Phase 3-4)
  ├─ Execute: Paper trading (Phase 3)
  ├─ Record: Actual entry/exit slippage per trade
  ├─ Monitor: Win rate, cumulative P&L
  ├─ Execute: Live trading (Phase 4, if Phase 3 passes)
  ├─ Monitor: Daily/weekly returns, DD
  ├─ Enforce: Emergency stops (3 losing days, >5% DD)
  └─ Timeline: 2-4 weeks (Phase 3), 4-12 weeks (Phase 4)

Risk Officer (Phase 4)
  ├─ Enforce: DD limits (5% weekly, 8% monthly)
  ├─ Enforce: Position sizing (1% per trade)
  ├─ Monitor: Weekly returns vs targets
  ├─ Escalate: If emergency stop conditions met
  └─ Approve: Scale decisions (if profitable)
```

---

## WHAT FALSIFIES THE EDGE

```
Immediate STOP Signals:

Phase 1:  If win rate <40% over 100+ events          → Edge does not exist
Phase 2:  If OOS win rate <35% (>7% degradation)    → Curve-fit detected
Phase 3:  If actual slippage >2.0 pips consistently  → Model is wrong
Phase 4:  If monthly Sharpe <0.5 for ANY month      → Not profitable live

If ANY of these occur: Strategy is DEAD. Accept failure. Move on.

What WON'T stop it:
├─ Temporary losing streak (1-2 weeks)
├─ Single bad trade
├─ Market chop (isolated event)
└─ Regime change (temporary)

What WILL stop it:
├─ Statistical failure (Phase 1-2 metrics not met)
├─ Persistent underperformance (month+ of losses)
├─ Slippage doesn't match model
└─ Win rate doesn't match backtest (structural issue)
```

---

## SUCCESS PROBABILITY ASSESSMENT

```
Estimated Probability:

Phase 1 (Backtest passes)?
└─ Probability: 40-50%
   Reason: Volatility clustering is real, but forced liquidations 
           might not persist through first 4 bars as expected.
           
Phase 2 (OOS passes | Phase 1 pass)?
└─ Probability: 70-80%
   Reason: If Phase 1 passes, OOS degradation <5% is likely
           (edge is based on documented microstructure, not curve-fit)
           
Phase 3 (Paper passes | Phase 2 pass)?
└─ Probability: 85-90%
   Reason: If Phase 2 works, slippage model should match reality
           within ±0.5 pips (EURUSD is highly liquid)
           
Phase 4 (Live profitable | Phase 3 pass)?
└─ Probability: 75-85%
   Reason: If Phase 3 validates model, live trading should work
           (real market conditions match paper trading environment)

Overall Probability (all 4 phases pass):
└─ 40% × 75% × 87% × 80% ≈ 21%
   = 1 in 5 chance this becomes a live, profitable strategy

Is 21% worth the effort?
└─ YES, because:
   ├─ If it works, strategy is production-ready
   ├─ If it fails, failure mode is known (not random decay)
   ├─ Learning compounds: Condition 2/3 edges get refined process
   └─ Cost: 2-3 weeks dev work (not high sunk cost)
```

---

## TIMELINE

```
Week 1-2:  Phase 1 Backtest
           ├─ Day 1-2: Data prep + S8 implementation
           ├─ Day 3-5: Backtest 5 years EURUSD
           └─ Day 6-7: Analysis + PASS/FAIL decision

Week 3:    Phase 2 Out-of-Sample (if Phase 1 passed)
           ├─ Day 1-2: Run OOS test on 2024-2025 data
           └─ Day 3: Analysis + PASS/FAIL decision

Week 4-7:  Phase 3 Paper Trading (if Phase 2 passed)
           ├─ Week 1-4: Daily trading + monitoring
           └─ End: Slippage validation + PASS/FAIL decision

Week 8-19: Phase 4 Live Trading (if Phase 3 passed)
           ├─ Week 1-4: Monthly performance check
           ├─ Week 5-8: Ongoing monitoring
           └─ Week 9-12: Scale decision (if profitable)

Total:     ~6-8 weeks to PROVE edge or ACCEPT failure
```

---

## INFRASTRUCTURE IMPACT

```
✅ Preserved:
├─ S1-S7 strategies (unaffected)
├─ Cost model (no changes)
├─ Bar contract (no changes)
├─ DD guard (still active)
└─ Regime engine (reused)

✅ Added (Non-Breaking):
├─ ATR percentile rank function
├─ Compression detection function
├─ S8 strategy module
├─ S8 regression tests
└─ S8 config params

✅ Disabled (If Edge Fails):
└─ S8 strategy (removed from enabled list)

Result: ZERO risk to existing infrastructure
```

---

## NEXT ACTION

```
Immediate (Today):
├─ [ ] Stakeholder reviews: README_EDGE_FIRST_REFACTORING.md
├─ [ ] Dev reviews: S8_IMPLEMENTATION_BLUEPRINT.md
├─ [ ] Trader reviews: DECISION_TREE_S8_VALIDATION.md
└─ [ ] Team alignment meeting (30 min)

This Week:
├─ [ ] Confirm EURUSD data availability (2020-2025)
├─ [ ] Allocate dev resources (1-2 days)
└─ [ ] Schedule Phase 1 backtest

Next Week:
├─ [ ] Phase 1 implementation begins
├─ [ ] Data infrastructure functions coded
└─ [ ] S8 strategy module built

Week 2:
├─ [ ] Phase 1 backtest execution
├─ [ ] Results analyzed
└─ [ ] GO/NO-GO decision made
```

---

**STATUS**: READY FOR PHASE 1 IMPLEMENTATION  
**TIMELINE**: 1-2 weeks Phase 1, then 4-6 weeks total (if all phases pass)  
**COMMITMENT**: If any phase fails, strategy is DEAD. No exceptions.  

**Let's validate this edge rigorously or accept it doesn't exist.**

---

*Version 1.0 | February 1, 2026*
