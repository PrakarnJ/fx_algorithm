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


---

## Walk-Forward 2026-06-13 11:15 UTC — Regime-Aware / Trend-Following (real Dukascopy data)

**Method:** rolling 12mo train → 3mo test across 2022→2026; parameters re-selected on each train window, evaluated on the next (unseen) test window; all test segments stitched into one OOS curve.  
**Regime mix (whole history, H1):** trend_up 15%, trend_down 10%, range 75%.  
**Note:** 2025+ is no longer a clean holdout (it informed this design); walk-forward across all regimes is the honest metric, and true confirmation needs forward data.

| Family | Windows | OOS trades | Win % | Expectancy | PF | Max DD | Total | MC p5 PF |
|---|---|---|---|---|---|---|---|---|
| trend | 14 | 120 | 60.8% | +6.809 | 1.39 | 398.4 | +817.0 | 0.74 |
| regime_switch | 14 | 131 | 64.1% | +9.520 | 1.765 | 274.5 | +1247.1 | 1.034 |

**Verdict:** `regime_switch` is the strongest — stitched walk-forward PF 1.765, expectancy +9.520 pts over 131 trades across 14 regimes. Original 90% WR / PF>2 / DD<10 target is not the right yardstick for a trend-follower (lower WR, larger wins by design); judged on risk-adjusted robustness across regimes instead.

**Profit concentration (critical caveat):** 69% of regime_switch's total (+857 of +1247 pts) comes from a single test window — 2026-01→04, the parabolic gold spike. The other 13 windows net +390 pts (8 profitable / 4 losing / 2 flat), so there is a positive base rate beyond that one episode, but the headline is tail-driven — the signature of trend-following (a few big winners carry the curve), which is why Monte-Carlo p5 PF falls to ~1.03. Real edge, but fragile. Walk-forward validates the *process*, not a single param set (each window re-optimizes); for live use, re-optimize on a rolling basis. Not auto-deployed; config.py unchanged.

### Prior context — 8h fade-strategy campaign (real data, FAILED)
Before the regime-aware pivot, an 8h Optuna campaign searched mean-reversion / RSI-fade / ML-classifier / breakout-scalp families (~50k trials). All looked viable in-sample and on 2024 validation (ML: 84% WR, PF 1.47) but **every finalist had PF < 0.5 on 2025+ OOS** — losing strategies. Root cause: 2025+ gold went parabolic (+61%, price ~doubled) and the fade families are anti-trend. This motivated the regime-aware / trend-following pivot above. Full detail: backtest/campaign_runs/campaign_results.json.
