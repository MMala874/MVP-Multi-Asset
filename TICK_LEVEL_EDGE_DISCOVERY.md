# TICK-LEVEL EDGE DISCOVERY: STATISTICAL FRAMEWORK
## Ricerca Strutturale Volatilità Compression → Return Distribution Shift

**Data**: February 1, 2026  
**Asset**: EURUSD (MT5 tick data, bid/ask)  
**Ipotesi**: Compressione volatilità tick-level → cambio significativo distribuzione rendimenti

---

## PROBLEMA CON S8 (Precedente)

S8 era **pattern-based**: 
- Entry su breakout percentile ATR
- Dipendeva da parametri (SL=10, TP=25)
- Logica "entra qui, esci lì"
- Risk: curve-fit, parameter optimization

**Pivot richiesto**: 
- NO pattern
- NO entry signal
- SI: evento statistico → distribuzione cambia
- Minimalismo strategico (solo attivazione, neutralità direzione)

---

## IPOTESI CENTRALE (UNA SOLA)

```
Evento: Volatility Compression Tick-Level
  ├─ realized_vol < percentile(5%)     [ultra basso)
  ├─ tick_count < percentile(10%)      [attività rarefatta)
  └─ spread_std < threshold             [spread stabile)

Conseguenza: Distribuzione rendimenti post-evento CAMBIA
  ├─ variance ↑
  ├─ tail risk ↑
  └─ skew shift ↑

👉 SE cambia significativamente (p < 0.05) → edge esiste
👉 SE non cambia → hypothesis false, STOP
```

**Cosa NON è**:
- ❌ Predizione direzione
- ❌ Segnale EMA/ADX
- ❌ Win rate alto
- ❌ Profit factor

**Cosa È**:
- ✅ Cambiamento regime statistico
- ✅ Opportunità di trading ATTIVAZIONE-based (non SEGNALE-based)
- ✅ Framework di sopravvivenza

---

## TASK A: FEATURE ENGINEERING (TICK-LEVEL)

### Data Requirements

```
Input: MT5 tick data EURUSD
  ├─ Timestamp (microsecondi, se disponibile)
  ├─ bid (prezzo bid)
  ├─ ask (prezzo ask)
  └─ volume (tick volume, spesso 1 per retail)

Output: Features rolling-window per ogni tick

Anti-lookahead: 
  ⚠️ Tutte le features calcolate BACKWARD ONLY
  ⚠️ Nessuna normalizzazione global (usa solo storia passata)
```

### 1. Volatility Compression Features (finestra 1, 5, 15 minuti)

```python
# Per ogni finestra rolling (es. 300 ticks = 1 min M15):

tick_range = max(bid_in_window) - min(bid_in_window)
  # ampiezza grezzo in ticks

realized_vol_ticks = std(bid_changes_in_window)
  # volatilità vera (deviazione std bid)

ticks_per_minute = count(ticks_in_window) / duration_minutes
  # frequenza ticks

avg_inter_tick_time = mean(timestamp_delta_between_ticks)
  # tempo medio tra ticks (secondi)

std_inter_tick_time = std(timestamp_delta_between_ticks)
  # variabilità tempi inter-tick
  # HIGH = sporadico, LOW = costante

bid_price_levels = unique_prices_in_window
  # quanti livelli bid distinti

ask_price_levels = unique_prices_in_window
  # quanti livelli ask distinti

orderbook_density = bid_price_levels / tick_range
  # densità prezzi (fitto vs sparse)
```

### 2. Spread Regime Features

```python
spread = ask - bid
  # spread istantaneo (al bid tick)

spread_mean = mean(spread_in_window)
spread_std = std(spread_in_window)
spread_min = min(spread_in_window)
spread_max = max(spread_in_window)

spread_spike_flag = (spread > 2 * spread_mean)
  # flag se spread allarga > 2x media

spread_stability_ratio = spread_std / spread_mean
  # rapporto variabilità/media
```

### 3. Market Activity Features

```python
tick_count = count(ticks_in_window)
  # numero ticks grezzo

tick_count_pct = percentile_rank(tick_count, lookback=250)
  # rank percentile storico (0-100)

burst_ratio = tick_count / mean(tick_count_trailing_100_windows)
  # rapporto attività corrente vs media storica

buy_sell_imbalance = abs(buy_ticks - sell_ticks) / total_ticks
  # imbalance direzionale (se disponibile)

price_stickiness = count(same_price_consecutive_ticks) / tick_count
  # % ticks stesso prezzo
  # ALTO = poco volume, BASSO = attivo
```

### 4. Compressione FLAG

```python
compression_flag = (
    realized_vol_ticks < percentile(realized_vol_ticks, 5) AND
    tick_count < percentile(tick_count, 10) AND
    spread_std < threshold_spread
)

# Output: Serie temporale di 1/0 per ogni finestra rolling
# 1 = finestra in compressione
# 0 = finestra normale
```

---

## TASK B: STATISTICAL TEST (NO TRADING)

### Event Definition

```
Per ogni window rolling identificata come COMPRESSION:

EVENT_START = timestamp window compressione

LOOKBACK_PERIOD = ultimi 30 minuti prima EVENT_START
FORWARD_PERIOD = prossimi 5, 15, 30 minuti dopo EVENT_START

Identificare tutti gli eventi (es. 100-500 nel dataset)
```

### Return Calculation (Tick-Level)

```python
# Per ogni evento, calcolare forward returns a 3 horizon:

1. forward_return_5m = (bid_price[t+5min] - bid_price[t]) / bid_price[t]
2. forward_return_15m = (bid_price[t+15min] - bid_price[t]) / bid_price[t]
3. forward_return_30m = (bid_price[t+30min] - bid_price[t]) / bid_price[t]

# Usare BID price (non mid, per realisticità costi)
```

### Statistical Measures (Per ogni return horizon)

```
Per distribution dei return CONDIZIONATI all'evento (|EVENT):

mean_return_given_event = mean(forward_returns | EVENT)
std_return_given_event = std(forward_returns | EVENT)
skew_given_event = skewness(forward_returns | EVENT)
kurtosis_given_event = kurtosis(forward_returns | EVENT)

CVaR_95_given_event = mean(bottom 5% returns | EVENT)
  # tail risk: perdita media nel peggior 5%

var_95_given_event = percentile(forward_returns | EVENT, 5)
  # VaR al 95%
```

### Comparison: EVENT vs NO-EVENT

```
Creare gruppo CONTROL (no compression):

mean_return_no_event = mean(forward_returns | NO EVENT)
std_return_no_event = std(forward_returns | NO EVENT)
skew_no_event = skewness(forward_returns | NO EVENT)
CVaR_95_no_event = mean(bottom 5% returns | NO EVENT)

Calcolare differenze:
Δmean = mean_given_event - mean_no_event
Δstd = std_given_event - std_no_event
Δskew = skew_given_event - skew_no_event
ΔCVaR = CVaR_given_event - CVaR_no_event
```

### Permutation Test (Significance)

```
Null hypothesis: 
  H0 = P(returns | EVENT) = P(returns | NO EVENT)

Procedura:
1. Calcolare test statistic osservato (es. Δmean)
2. Shufflare event labels 1000 volte
3. Per ogni shuffle, calcolare test statistic
4. Contare quante volte shuffled > osservato
5. p_value = count_shuffled / 1000

SE p_value < 0.05: rifiuta H0, cambio distribuzione è REALE
SE p_value > 0.05: non rifiutare H0, cambio è RANDOM → STOP
```

### Bootstrap Confidence Interval

```
Per ogni metrica (mean, std, skew):

1. Resample events con replacement 1000 volte
2. Calcolare metrica su ogni resample
3. Percentile 2.5% e 97.5% = CI 95%

Output: confidence interval per ogni effetto

SE CI include 0: effetto non significativo
```

---

## TASK C: EDGE DECISION (DECISION TREE)

```
Analisi post-test:

┌─ È p_value < 0.05 (cambio significativo)?
│
├─ NO → STOP. Edge non esiste. Return to drawing board.
│
└─ YES ↓
   
   ┌─ Varianza AUMENTA? (std_given_event > std_no_event)
   │
   ├─ NO → Cambio distribuzione ma NO tail risk → Utility bassa
   │       (edge è débile, skip)
   │
   └─ YES ↓
      
      ┌─ Tail risk AUMENTA? (CVaR piu negativo quando evento)
      │
      ├─ NO → Varianza ↑ ma tail stabile → Utility media
      │       (qualcosa succede, ma non pericoloso)
      │
      └─ YES ↓
         
         ┌─ Skew CAMBIA? (da negativo → positivo, o vice versa)
         │
         ├─ NO → Tail up, varianza up, ma distribuzione stabile
         │       (utility media-bassa)
         │
         └─ YES ↓
            
            ✅ EDGE ATTIVABILE
            
            Significato:
            • Compressione precede REGIME CHANGE
            • Non direzione (skew può essere up o down)
            • Ma ASIMMETRIA → opportunità
```

### Edge Activation Logic (NOT Trading Signal)

```
Se tutte le condizioni di Task C sono MET:

EDGE_ACTIVE = True

Cosa significa:
  ❌ NOT "compra qui"
  ❌ NOT "vendi lì"
  ✅ YES "il mercato ha proprietà diverse"
  ✅ YES "posso fare piccoli trade NEUTRI con bias HTF"

Action:
  ├─ Aspetta compressione evento
  ├─ Entra NEUTRO (no directional signal)
  │  oppure con BIAS da H1/H4 semplice (ema_fast > ema_slow only)
  ├─ SL fisso e CORTO
  ├─ EXIT su time (5-15 min)
  └─ Max 1 trade per evento
```

---

## TASK D: OPERATIONAL STRATEGY (MINIMAL)

### Entry Rules (If Edge Activated)

```
PRECONDIZIONI:
  • compression_flag = 1 (evento in corso)
  • p_value < 0.05 (da Task B)
  • No position open

ENTRY LOGIC:

Option A: NEUTRAL (no directional bias)
  ├─ Signal LONG = breakout above recent high + spread < 1.5 pips
  ├─ Signal SHORT = breakout below recent low + spread < 1.5 pips
  ├─ Quantità: 0.01 lot (micro position)
  └─ Probabilità: ~50% per direzione (pure attivazione)

Option B: HTF BIAS (semplice, no complexity)
  ├─ Calcolare EMA_50 su H4 chiusi
  ├─ Se EMA_fast_H4 > EMA_slow_H4: LONG bias (LONG entry prioritaria)
  ├─ Se EMA_fast_H4 < EMA_slow_H4: SHORT bias
  ├─ Entry: close breakout in direzione bias
  ├─ Quantità: 0.01 lot
  └─ Timeout entry: 5 min (se non triggera, skip)
```

### Exit Rules

```
TIME-BASED EXIT (primary):
  ├─ Se entrato, uscire dopo 5-15 min (esatto)
  ├─ Exit al bid (aspetta riempimento)
  └─ No discretion

HARD SL:
  ├─ SL = 12-15 pips fissi (non negoziale)
  ├─ If hit: STOP immediato (accetta loss)
  └─ Motivation: tight SL = sopravvivenza

NO FIXED TP:
  ❌ Non usare TP fisso (es. 20 pips)
  ✅ Solo time-based exit

MAX LOSS STREAK:
  ├─ If 3 consecutive losses: PAUSE 2 ore
  ├─ If 5 consecutive losses in day: STOP rest of day
  └─ Obiettivo: preservare equity, non forzare
```

### Position Sizing

```
Risk per trade: 0.01 lot = $1000 notional (micro)
  
Giustificazione:
  • SL 12 pips = max loss $12 per trade
  • 50 trade al mese = max -$600 (sopportabile)
  • DD massimo target: 3-5% account
  • Low frequency (1-2 trade per evento)
```

### Trade Journal Minimum

```
Per ogni trade registrare:

timestamp_entry
compression_event_duration (quanti min di compressione prima)
entry_price
entry_direction (LONG/SHORT)
spread_at_entry
tick_volume_at_entry
exit_timestamp
exit_price
P&L_pips
market_conditions_at_exit (compression_over? trend_started?)
```

---

## TASK E: SURVIVAL TEST (Backtesting)

### Backtest Protocol

```
Input:
  • MT5 tick data EURUSD 2023-2025 (minimo 2 anni)
  • Compression detection algorithm (Task A)
  • Event filtering (Task B statistical validation)

Run:
  1. Identificare tutti compression event nel dataset
  2. Per ogni evento, simulare entry/exit rigido (Task D)
  3. Registrare P&L, durata trade, condizioni di exit
  4. Calcolare equity curve

Output Metrics:
```

### Survival-Focused Metrics (NOT Profit)

```
❌ Non vogliamo:
  • Profit factor alto (es. 2.0)
  • Win rate alto (es. 60%)
  • Sharp alto (es. 1.5)
  
✅ Vogliamo:
  • Max DD < 5% account
  • Consecutive losses < 5 (raro)
  • Equity curve "noiosa" (lenta, non altalena)
  • Trade count basso (<50/anno)
```

### Key Metrics

```
1. Drawdown Analysis
   • Max DD: ___% (target < 5%)
   • Drawdown duration (giorni): ___ (target < 10)
   • DD condizionato (durante compressione): ___% (target < 3%)

2. Loss Streak
   • Max consecutive losses: ___ (target < 5)
   • Probability 3+ loss streak: ___% (target < 10%)

3. Trade Quality
   • Avg P&L per trade: ___ pips (target > 0)
   • Win% non required (✅ anche 45% va bene se survival)
   • Avg trade duration: ___ min (target 5-20)

4. Equity Curve
   • Smoothness (Calmar ratio): ___
     High Calmar = equity tranquilla
     Low Calmar = altalena erratica
   • Target: Calmar > 0.3

5. Kill-Switch Effectiveness
   • Dopo max loss streak → PAUSE riduceva future DD?
   • YES → kill-switch funziona
   • NO → kill-switch inefficace
```

### Red Flags (STOP)

```
Se osservato nel backtest:

1. Max DD > 8%
   → Strategia troppo aggressiva o edge inesistente
   → STOP, revisare
   
2. Max consecutive losses > 7
   → SL non protegge, eventi false alarm
   → STOP
   
3. Win rate < 35%
   → Trop random, no edge
   → STOP
   
4. Equity curve monotona decrescente
   → Costi erodono edge
   → STOP
```

### Green Lights (PROCEED)

```
Se osservato:

1. Max DD 3-5%
2. Max consecutive losses 3-4
3. Win rate 40-50% (neutrale)
4. Avg P&L > 0
5. Equity curve "noiosa" (non altalena)
6. < 30 trade/anno

👉 Procedere a Phase 2 (paper trading)
```

---

## IMPLEMENTATION ROADMAP

### Phase 0: Feature Engineering (2-3 giorni)

```
1. Acquistare/scaricare MT5 tick data EURUSD 2023-2025
2. Parse tick data (bid, ask, time)
3. Implementare Task A features (compression_flag, etc.)
4. Verificare no lookahead
5. Produrre feature dataset
```

### Phase 1: Statistical Test (2 giorni)

```
1. Definire compression events (Task B)
2. Calcolare return distributions (given event vs no event)
3. Permutation test + bootstrap
4. Output: p_value, effect size, CI
5. Decision: edge esiste? (Task C)
```

### Phase 2: Backtest (1 giorno)

```
1. Implementare trading rules (Task D)
2. Run simulator su full dataset
3. Raccogliere metrics (Task E)
4. Check red flags vs green lights
```

### Phase 3: Paper Trading (se Phase 1-2 passano)

```
1. Implementare live feature calc (real-time ticks)
2. Paper trade 2-4 weeks
3. Monitor: slippage, fill quality, actual DD
4. Compare: backtest vs paper
```

### Phase 4: Live (se Phase 3 passa)

```
1. Live trade 1% account
2. Monitor DD, kill-switch triggers
3. Decision: scale o stop?
```

---

## CRITICAL ASSUMPTIONS

```
Hypothesis: Compressione volatilità tick-level 
           → cambio distribuzione rendimenti 
           → opportunità trading

Se Phase 1 statistical test FALLISCE (p > 0.05):
  → Hypothesis è FALSE
  → Edge non esiste
  → STOP ricerca
  
Se Phase 1 PASSA (p < 0.05):
  → Cambio distribuzione è REALE
  → Phase 2 backtest determina sopravvivenza
  → Se backtest passa (DD < 5%): proceedi
  → Se backtest fallisce: revisare rules, re-test
```

---

## FORBIDDEN PRACTICES

```
❌ Stacking indicatori
   (no combo: compression + RSI + Bollinger, etc.)
   
❌ ML black box
   (no neural net, no random forest)
   
❌ Ratio risk/reward fisso
   (no "sempre SL:TP = 1:3")
   
❌ Parameter optimization
   (no grid search su windows, threshold, etc.)
   
❌ Curve-fitting
   (freeze parameters Phase 1, test Phase 2+)
   
❌ Pattern recognition post-hoc
   (no "saw this candle pattern, added signal")
```

---

## SUCCESS DEFINITION

Non è strategia vincente.

È **validazione statistica** che:

1. ✅ Compressione tick-level precede cambio distribuzione (p < 0.05)
2. ✅ Cambio è asimmetrico e tail-positive (opportunità)
3. ✅ Trading operativo su questo è SOPRAVVIVIBILE (DD < 5%)
4. ✅ Trade frequency bassa (<50/anno)
5. ✅ Equity curva "noiosa" non "altalena"

Se tutto TRUE: edge è REALE (probabilistico, non deterministico)

Se uno FALSE: torna a Task A/B/C, revisiona.

---

## PROSSIMI STEP

1. [ ] Confermare disponibilità tick data MT5 (EURUSD 2023-2025)
2. [ ] Setup Python + librerie (pandas, numpy, scipy, matplotlib)
3. [ ] Implementare Task A (feature engineering)
4. [ ] Implementare Task B (statistical test)
5. [ ] Runmare permutation test su campione
6. [ ] Decision: edge esiste? → sì/no
7. [ ] Se sì: Task D implementation + backtest
8. [ ] Se no: STOP, accept failure, try new hypothesis

---

**Status**: Framework definito, pronto per implementazione  
**Commitment**: Accettare risultato test (PASS/FAIL), no wishful thinking  
**Timeline**: 1 settimana ricerca + statistical validation

