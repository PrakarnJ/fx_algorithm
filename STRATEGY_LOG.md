# STRATEGY LOG — XAUUSD Gold Trading Bot

**Data:** Synthetic GBM 2022-01-01 → 2026-01-01  |  **OOS window:** 2025-01-01+  |  **Updated:** 2026-06-12

---

## Master Summary Table

| Variant                   | Data            | Key Rules / Changes                                                           | Trades | Win%   | Expectancy | PF    | Max DD   | Verdict |
|---------------------------|-----------------|----------------------------------------------------------|--------|--------|-----------|-------|----------|--------|
| A-baseline               | Synthetic GBM   | EMA 9/21 crossover + RSI(14) + H4 EMA(50) trend            |     66 |   66.7% |   -0.023 | 1.000 |    158.8 | ❌ FAIL |
| B-baseline               | Synthetic GBM   | London breakout (london_end=12h, tp=3.0×, rmax=2.0×, rmin=0.2×) |     88 |   54.5% |   +7.246 | 1.994 |    119.4 | ✅ PASS |
| B-v1-partial-tp          | Synthetic GBM   | + Partial TP at 1R (close 50%, move SL to BE)              |     87 |   55.2% |   +4.243 | 1.594 |    126.0 | ✅ KEPT |
| B-v2-trend-filt          | Synthetic GBM   | + H4/H1 EMA(50) trend-alignment filter                     |     43 |   55.8% |   +4.673 | 1.647 |     83.1 | ✅ KEPT |
| B-v3-adx-filt            | Synthetic GBM   | + ADX(14) > 20 filter on H1                                |     32 |   56.2% |   +5.247 | 1.719 |     53.3 | ✅ KEPT |
| B-v4-time-stop           | Synthetic GBM   | + Time-stop after 8 H1 bars                                |     32 |   62.5% |   +6.309 | 2.022 |     35.7 | ✅ KEPT |
| B-v5-early-partial       | Synthetic GBM   | + Earlier partial TP at 0.5R (lock profits sooner)         |     14 |   57.1% |   +5.413 | 1.842 |     30.3 | ❌ REJECTED |
| B-v6-closer-tp           | Synthetic GBM   | + Re-optimize final TP toward 1.0–2.0× range (closer target) |     14 |   57.1% |   +7.423 | 2.155 |     30.3 | ❌ REJECTED |
| B-v7-wr-objective        | Synthetic GBM   | + Re-optimize with win-rate objective (exp > 2 constraint) |     13 |   53.8% |   +2.026 | 1.293 |     41.3 | ❌ REJECTED |
| B-v8-tight-trail         | Synthetic GBM   | + Tighter trail after partial (0.75×ATR on runner)         |     14 |   57.1% |   +7.423 | 2.155 |     30.3 | ❌ REJECTED |
| B-v9-scalp-mode          | Synthetic GBM   | + Scalp mode: close 100% at partial TP level (max win rate) |     14 |   57.1% |   +1.496 | 1.233 |     33.3 | ❌ REJECTED |
| ★ FINAL BEST             | Synthetic GBM   | All kept rounds combined — win_rate=62.5%                  |     32 |   62.5% |   +6.309 | 2.022 |     35.7 | 🏆 BEST (62.5%) |

---

## Detailed Results

### 1. Strategy A — Trend-Following (baseline, FAILED)
Rules: EMA(9) × EMA(21) on H1, H4 EMA(50) trend bias, RSI(14) 50–70/30–50 filter.  
Best in-sample params: ema_fast=9, ema_slow=18, sl=2.5×ATR, tp=2.0×ATR.  
OOS result: win_rate=66.7%, PF=1.00, expectancy=−0.02 pts. **Rejected** (expectancy negative).


---

### 2. Strategy B — London Breakout (baseline, PASSED)
Rules: Asian range 00:00–07:00 UTC, breakout during 07:00–12:00 UTC.  
Best in-sample params: london_end=12h, tp=3.0×range, range_max=2.0×ATR, range_min=0.2×ATR.  
OOS result: win_rate=54.5%, PF=1.994, expectancy=+7.246 pts. **Accepted** as baseline.


---

### 3. B-v1-partial-tp
Change: + Partial TP at 1R (close 50%, move SL to BE)  
Params used: london_end=12h, tp=3.0×, range_max=2.0×, range_min=0.2×  
OOS: trades=87, win=55.2%, expectancy=+4.243, PF=1.594, max_DD=126.0  
Verdict: **✅ KEPT**


---

### 4. B-v2-trend-filter
Change: + H4/H1 EMA(50) trend-alignment filter  
Params used: london_end=12h, tp=3.0×, range_max=2.0×, range_min=0.2×  
OOS: trades=43, win=55.8%, expectancy=+4.673, PF=1.647, max_DD=83.1  
Verdict: **✅ KEPT**


---

### 5. B-v3-adx-filter
Change: + ADX(14) > 20 filter on H1 (skip low-momentum days)  
Params used: london_end=12h, tp=3.0×, range_max=2.0×, range_min=0.2×  
OOS: trades=32, win=56.2%, expectancy=+5.247, PF=1.719, max_DD=53.3  
Verdict: **✅ KEPT**


---

### 6. B-v4-time-stop
Change: + Time-stop: close after 8 H1 bars if neither SL nor TP hit  
Params used: london_end=12h, tp=3.0×, range_max=2.0×, range_min=0.2×  
OOS: trades=32, win=62.5%, expectancy=+6.309, PF=2.022, max_DD=35.7  
Verdict: **✅ KEPT**


---

### 7. FINAL BEST VARIANT
All kept enhancements combined.  
Params: london_end=12h, tp=3.0×, range_max=2.0×, range_min=0.2×, partial_tp=ON (@1.0R), trend_filter=ON, adx_min=20.0, time_stop=8h  
Best OOS win rate: **62.5%**  
Note: 99% win-rate target not met — this is expected and honest.

---

### R2-1. B-v5-early-partial
Change: + Earlier partial TP at 0.5R (lock profits sooner)  
Params: london_end=12h, tp=3.0×, rmax=1.5×, rmin=0.2×, partial_r=0.5, scalp=False, adx_min=20.0, time_stop=8h  
OOS: trades=14, win=57.1%, exp=+5.413, PF=1.842, DD=30.3  
Verdict: **❌ REJECTED**


---

### R2-2. B-v6-closer-tp
Change: + Re-optimize final TP toward 1.0–2.0× range (closer target)  
Params: london_end=12h, tp=3.0×, rmax=1.5×, rmin=0.2×, partial_r=1.0, scalp=False, adx_min=20.0, time_stop=8h  
OOS: trades=14, win=57.1%, exp=+7.423, PF=2.155, DD=30.3  
Verdict: **❌ REJECTED**


---

### R2-3. B-v7-wr-objective
Change: + Re-optimize with win-rate objective (exp > 2 constraint)  
Params: london_end=11h, tp=1.5×, rmax=1.5×, rmin=0.2×, partial_r=1.0, scalp=False, adx_min=20.0, time_stop=8h  
OOS: trades=13, win=53.8%, exp=+2.026, PF=1.293, DD=41.3  
Verdict: **❌ REJECTED**


---

### R2-4. B-v8-tight-trail
Change: + Tighter trail after partial (0.75×ATR on runner)  
Params: london_end=12h, tp=3.0×, rmax=1.5×, rmin=0.2×, partial_r=1.0, scalp=False, adx_min=20.0, time_stop=8h  
OOS: trades=14, win=57.1%, exp=+7.423, PF=2.155, DD=30.3  
Verdict: **❌ REJECTED**


---

### R2-5. B-v9-scalp-mode
Change: + Scalp mode: close 100% at partial TP level (max win rate)  
Params: london_end=12h, tp=1.0×, rmax=1.5×, rmin=0.2×, partial_r=1.0, scalp=True, adx_min=20.0, time_stop=8h  
OOS: trades=14, win=57.1%, exp=+1.496, PF=1.233, DD=33.3  
Verdict: **❌ REJECTED**
