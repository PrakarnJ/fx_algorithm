# FX Algorithm Platform

Multi-asset algorithmic trading research platform with a FastAPI backend, React frontend, and backtesting engine.

**Best strategy (XAUUSD):** `regime_switch` — composite Donchian trend-follower + z-score mean-reversion router. Walk-forward OOS on real Dukascopy 2022–2026 data: **PF 1.77, 64% WR, Sharpe 2.38, +1,247 pts** over 131 trades. Backtested result only — see [Validation status](#validation-status).

## How the platform works

```
┌──────────────────────────────────────────────┐
│  React frontend  (Vite · Tailwind · SWR)      │  :5173 (dev) / :8000 (prod)
│  Dashboard · Backtest · Replay · Data · Logs  │
└──────────────────┬───────────────────────────┘
                   │  HTTP + WebSocket
┌──────────────────▼───────────────────────────┐
│  FastAPI backend  (uvicorn · :8000)            │
│  /api/algorithms  /api/backtest  /api/replay   │
│  /api/stocks      /api/logs                    │
└──────────────────┬───────────────────────────┘
                   │
┌──────────────────▼───────────────────────────┐
│  algorithms/  ← single source of truth        │
│  7 strategies + registry + base               │
│  backtest/engine  metrics  walkforward …      │
└──────────────────────────────────────────────┘
```

The **algorithms/** directory is the single source of truth — the backtest engine and the API both import from there.

## How the best strategy works

`regime_switch` detects the market **regime** and routes to the matching tactic:

- **Trending** (ADX strong + Kaufman efficiency ratio high + price vs EMA200) → **Donchian breakout trend-follower**: enter with the move, ride it with an ATR trailing stop (no fixed TP).
- **Ranging** (everything else, ~75% of the time) → **z-score mean-reversion** fade, or stand aside (current config rides trends only).

The single most important lesson driving this design: **no one tactic works in all regimes.** Fade strategies print money in ranges and blow up in trends; trend-followers do the reverse.

## Strategies tried (the honest journey)

| Strategy | Data | OOS result | Verdict |
|---|---|---|---|
| Trend-Following (EMA crossover) | synthetic | negative expectancy | ❌ |
| London Breakout (+ boosters) | synthetic | 62.5% WR, PF 2.02 | ⚠️ synthetic-only artifact |
| Mean-reversion / RSI-fade / ML (8h Optuna campaign) | **real** | every finalist **PF < 0.5** | ❌ killed by 2025+ bull |
| **Regime-Aware Switch** | **real** | **PF 1.77 walk-forward** | ✅ best |

Full blow-by-blow in `STRATEGY_LOG.md`. Synthetic "winners" were fictions of the data generator; on real gold they lose.

## Setup

### Backend (Python)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### Frontend (Node.js)

```bash
cd frontend
npm install
npm run dev          # Vite dev server → http://localhost:5173
# npm run build      # production build → frontend/dist/ (served by FastAPI)
```

### Data

Get real gold data via the free Dukascopy feed:

```bash
npx dukascopy-node -i xauusd -from 2022-01-01 -to 2026-06-13 -t m15 -f csv -dir /tmp/duka
npx dukascopy-node -i xauusd -from 2022-01-01 -to 2026-06-13 -t h1  -f csv -dir /tmp/duka
npx dukascopy-node -i xauusd -from 2022-01-01 -to 2026-06-13 -t h4  -f csv -dir /tmp/duka
.venv/bin/python3 data/convert_dukascopy.py /tmp/duka   # → data/XAUUSD_{M15,H1,H4}.csv
```

Or generate synthetic bars for pipeline testing (not a real edge):

```bash
.venv/bin/python3 data/generate_synthetic.py
```

Multi-asset data (AAPL, MSFT, SPY, BTCUSD, …) is downloaded via the web UI's **Data** page or:

```bash
.venv/bin/python3 -c "from data_pipeline.downloader import download; from config import STOCKS_DIR; download('XAUUSD', 'GC=F', ['M15','H1','H4'], STOCKS_DIR)"
```

## Usage

### Web platform (API + frontend)

```bash
# Backend
.venv/bin/python3 -m uvicorn api.main:app --reload --port 8000

# Frontend dev server (separate terminal)
cd frontend && npm run dev
# → open http://localhost:5173
```

Pages: **Dashboard** (rankings) · **Backtest** (run algo×symbol jobs) · **Replay** (bar-by-bar playback) · **Data** (download/manage CSVs) · **Logs** (live event stream)

### Backtest pipeline (CLI)

```bash
.venv/bin/python3 backtest/smoke_test.py          # strategy sanity checks
.venv/bin/python3 backtest/compare.py             # head-to-head: trend vs breakout
.venv/bin/python3 backtest/walkforward.py --family all --trials 40  # rolling WFO
.venv/bin/python3 backtest/campaign.py --budget-hours 8             # Optuna campaign
```

### Re-optimization (keep params fresh)

```bash
.venv/bin/python3 backtest/reoptimize.py                # optimize → propose
.venv/bin/python3 backtest/reoptimize.py --no-download  # skip download step
.venv/bin/python3 backtest/reoptimize.py --apply        # apply proposal to config
```

Writes `data/regime_params.json`; loaded by `config.py` at import time — delete to revert to hardcoded defaults.

### Legacy Control Center (original dashboard)

```bash
.venv/bin/python3 backtest/export_report.py        # regenerate report/data.json
.venv/bin/python3 backtest/dashboard_server.py --port 8765
# → http://localhost:8765   tabs: #overview #performance #optimize #deploy
```

## Project layout

```
config.py                     # symbol, SharedParams + all strategy params, REGIME_PARAMS
indicators.py                 # EMA, RSI, ATR, ADX (Wilder)
trade_manager.py              # break-even + ATR trailing SL (shared by engine)
risk_manager.py               # lot sizing, drawdown guard (loss-streak pause, daily stop)

algorithms/                   # ★ single source of truth for all strategies
  base.py                     # Signal dataclass (with SL/TP validation), BaseStrategy
  registry.py                 # AlgoManifest registry; TF_TO_FILE / TF_TO_YF maps
  trend_following.py          # EMA(9/21) crossover + H4 bias + RSI filter
  london_breakout.py          # Asian-range London open breakout
  mean_reversion.py           # z-score fade (fixed TP/SL)
  rsi_fade.py                 # RSI-extreme fade scalper
  trend_breakout.py           # Donchian / MA-momentum with ATR trail
  ml_classifier.py            # gradient-boosted TP-before-SL classifier
  regime_switch.py            # ★ best: regime-aware composite

api/                          # FastAPI backend
  main.py                     # app, CORS, router mounts, static frontend serving
  schemas.py                  # Pydantic v2 request/response models
  runner.py                   # BacktestRunner: job queue + WS broadcast
  replay_engine.py            # ReplaySession: pre-compute frames, stream over WS
  routers/
    algorithms.py             # GET /api/algorithms
    backtest.py               # POST /api/backtest/run + WS /ws/backtest/{job_id}
    replay.py                 # POST /api/replay/start + WS /ws/replay/{session_id}
    stocks.py                 # CRUD + download for symbol data
    logs.py                   # GET /api/logs

frontend/src/                 # React + TypeScript + Tailwind (Vite)
  pages/                      # DashboardPage · BacktestPage · ReplayPage · DataPage · LogsPage
  components/backtest/        # RunConfigForm · ProgressFeed
  components/replay/          # ChartPlayer · CandlestickChart · PlaybackControls
  components/dashboard/       # RankingTable · MetricBadge
  hooks/                      # useApi (SWR) · useReplayWebSocket
  lib/api.ts                  # typed apiFetch wrapper + all API interfaces

data_pipeline/
  downloader.py               # yfinance download → CSV (H4 resampled from H1)
  resampler.py                # H1 → H4 OHLC aggregation
  capabilities.py             # check CSV exists + MIN_BARS threshold per TF

stocks/
  registry.yaml               # symbol metadata: name, tick_size, spread, yfinance_ticker
  loader.py                   # load/query registry

backtest/
  engine.py                   # run_backtest_fast (vectorized) + run_backtest (reference) + replay_iter
  regime.py                   # classify_regime: ADX + EMA200 + Kaufman ER
  metrics.py                  # trade-frequency-aware Sharpe, PF, drawdown, R-multiples
  walkforward.py              # rolling train→test WFO; stitched OOS + Monte-Carlo bands
  montecarlo.py               # bootstrap robustness (CIs, skip-test, slippage)
  reoptimize.py               # optimize → walk-forward → propose → apply
  campaign.py                 # multi-family Optuna campaign (TRAIN/VAL/OOS)
  compare.py / optimize.py / walk_forward.py / iterate.py   # original head-to-head pipeline
  ml_features.py              # backward-looking features + TP-before-SL labels
  smoke_test.py               # no-look-ahead, live/backtest parity, engine regression
  export_report.py            # regenerate report/data.json
  dashboard_server.py         # legacy Control Center (Overview/Performance/Optimize/Deploy)

data/
  XAUUSD_{M15,H1,H4}.csv     # real bars (gitignored; download via Dukascopy)
  convert_dukascopy.py        # convert Dukascopy CSVs → pipeline format
  generate_synthetic.py       # synthetic GBM bars (pipeline testing only)

tests/
  conftest.py                 # make_bars / make_dfs / StubStrategy fixtures
  test_engine.py              # engine edge cases: partial TP, time-stop, costs, pause
  test_indicators.py          # EMA / RSI / ATR / ADX correctness
  test_signal.py              # Signal SL/TP validation

report/                       # legacy dashboard static UI (served by dashboard_server.py)
```

## Strategy interface

Every strategy in `algorithms/` implements two entry points that must stay in sync:

- `get_signal(dfs) → Signal | None` — incremental, used by the replay API on the latest bars.
- `generate_signals(dfs) → DataFrame` — vectorized over all history, used by the fast backtest engine (~100× faster).

`dfs` is a dict of UTC-indexed OHLC DataFrames keyed `"M15"`, `"H1"`, `"H4"`.

## Tests

```bash
.venv/bin/python3 -m pytest tests/ -v          # 30 tests: engine, indicators, signal
.venv/bin/python3 backtest/smoke_test.py       # strategy integration checks
```

## Backtest conventions

- Profits in price points (1 pt = $0.01 on XAUUSD).
- Spread applied to entry; SL checked before TP within the same bar (conservative fill).
- No look-ahead: `generate_signals` uses only data available at signal time.
- Walk-forward: parameters re-selected on each train window, evaluated on the next unseen test window; all segments stitched into one OOS curve.
- Sharpe annualized by actual trade frequency (not a fixed √252 assumption).

## Validation status

**The best strategy is validated on real data via walk-forward — but NOT proven for live trading.**

- Every decision metric comes from out-of-sample windows the optimizer never touched.
- **2025+ is no longer a clean holdout** (this design was informed by seeing it). The only true test is forward data.
- **Profit is tail-driven:** ~69% of the regime-switch's walk-forward profit came from a single 2026 trend window. Monte-Carlo p5 PF ≈ 1.03 — real edge, but fragile.
- Synthetic data validates the *pipeline*, never a market edge.
