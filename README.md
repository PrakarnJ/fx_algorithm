# XAUUSD Trading Bot

Automated XAUUSD (Gold) trading bot for MetaTrader 5. Candidate strategies are validated on **real Dukascopy gold data** via optimization + walk-forward out-of-sample testing; the winner is selected by `ACTIVE_STRATEGY` in `config.py` and traded live by `bot.py`.

**Current strategy: Regime-Aware Switch** — walk-forward OOS on real 2022–2026 data: **PF 1.77, 64% win rate, Sharpe 2.38, +1,247 pts** over 131 trades. Wired for **demo trading only** (never forward-tested; profit is tail-driven). See [Validation status](#validation-status) and `DEPLOYMENT.md`.

## How it works

The bot detects the market **regime** and routes to the matching tactic:

- **Trending** (ADX strong + Kaufman efficiency ratio high + price vs EMA200) → **Donchian breakout trend-follower**: enter with the move, ride it with an ATR trailing stop (no fixed TP).
- **Ranging** (everything else, ~75% of the time) → **z-score mean-reversion** fade, or stand aside (current live config rides trends only).

The single most important lesson driving this design: **no one tactic works in all regimes.** Fade strategies print money in ranges and blow up in trends; trend-followers do the reverse. The regime switch picks the right tool per regime.

## Strategies tried (the honest journey)

| Strategy | Data | OOS result | Verdict |
|---|---|---|---|
| Trend-Following (EMA crossover) | synthetic | negative expectancy | ❌ |
| London Breakout (+ boosters) | synthetic | 62.5% WR, PF 2.02 | ⚠️ synthetic-only artifact |
| Mean-reversion / RSI-fade / ML (8h Optuna campaign) | **real** | every finalist **PF < 0.5** | ❌ killed by 2025+ bull |
| **Regime-Aware Switch** | **real** | **PF 1.77 walk-forward** | ✅ best, demo-only |

Full blow-by-blow (every variant, metrics, verdicts, Monte-Carlo bands) is in `STRATEGY_LOG.md`. The synthetic "winners" were fictions of the data generator; on real gold they lose. The fade families died because 2025+ gold went parabolic (+61%) and they are anti-trend — which motivated the regime-aware / trend-following pivot.

## Strategy interface

Every strategy implements two entry points that must stay in sync:

- `get_signal(dfs)` — incremental, used by the live bot on the latest bars.
- `generate_signals(dfs)` — vectorized over all history, used by the fast backtest engine (~100× faster).

`dfs` is a dict of UTC-indexed OHLC DataFrames keyed `"M15"`, `"H1"`, `"H4"`.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install pandas numpy optuna scikit-learn
```

`MetaTrader5` (in `requirements.txt`) only installs on **Windows** — required for live trading, not for backtesting. On macOS/Linux, develop and backtest against CSVs in `data/`.

**Get real gold data** (recommended) via the free Dukascopy feed:

```bash
npx dukascopy-node -i xauusd -from 2022-01-01 -to 2026-06-13 -t m15 -f csv -dir /tmp/duka
npx dukascopy-node -i xauusd -from 2022-01-01 -to 2026-06-13 -t h1  -f csv -dir /tmp/duka
npx dukascopy-node -i xauusd -from 2022-01-01 -to 2026-06-13 -t h4  -f csv -dir /tmp/duka
.venv/bin/python3 data/convert_dukascopy.py /tmp/duka   # → data/XAUUSD_{M15,H1,H4}.csv
```

Or generate seeded synthetic bars for pipeline testing only (not a real edge):

```bash
.venv/bin/python3 data/generate_synthetic.py
```

## Usage

```bash
# Walk-forward validation of the regime-aware / trend families (the honest metric)
.venv/bin/python3 backtest/walkforward.py --family all --trials 40

# Smoke tests for the strategies (no-look-ahead, live/backtest parity, engine regression)
.venv/bin/python3 backtest/smoke_test.py

# Older head-to-head pipeline for the original two strategies
.venv/bin/python3 backtest/compare.py

# Multi-family Optuna campaign with Monte-Carlo robustness (TRAIN/VAL/OOS split)
.venv/bin/python3 backtest/campaign.py --budget-hours 8

# Live trading loop — Windows + MT5 terminal only (see DEPLOYMENT.md)
.venv/bin/python3 bot.py
```

Set `ACTIVE_STRATEGY` in `config.py` to `"regime_switch"`, `"trend"`, or `"breakout"`.

## Control Center (unified dashboard)

One web UI with four tabs — **Overview · Performance · Optimize · Deploy** — for monitoring, analysis, and live control.

```bash
.venv/bin/python3 backtest/export_report.py        # regenerate report/data.json (folds in walk-forward results)
.venv/bin/python3 backtest/dashboard_server.py --port 8765
# open http://localhost:8765   (tabs are deep-linkable: #overview, #optimize, …)
```

- **Overview** — headline KPIs, current strategy/params, stitched walk-forward equity curve.
- **Performance** — variant explorer, equity/drawdown, monthly P&L, distribution, sortable trade table, Monte-Carlo bands, full comparison.
- **Optimize** — run re-optimization (button or CLI), watch live progress, review the proposed params + walk-forward check, and **Apply** (propose-and-confirm).
- **Deploy** — live config, demo-first ladder, every CLI command.

The server wraps the CLI tools, so **every action has both a command and a UI button**. Charts use ECharts from a CDN; no build step.

## Auto re-optimize (keep params fresh)

Markets drift, so the strategy's parameters go stale. The re-optimize pipeline refreshes them: **download latest data → optimize on the last 12 months → walk-forward sanity check → propose**. It is *propose-and-confirm* — nothing goes live until you Apply (which writes `data/regime_params.json`, read by `config.py`; delete it to revert).

```bash
.venv/bin/python3 backtest/reoptimize.py                # full pipeline → writes a proposal
.venv/bin/python3 backtest/reoptimize.py --no-download  # skip the Dukascopy download
.venv/bin/python3 backtest/reoptimize.py --apply        # apply the latest proposal to live config
.venv/bin/python3 backtest/reoptimize.py --install-cron # monthly schedule (1st of month, 06:00)
```

The same actions are available as buttons on the dashboard's **Optimize** tab. The monthly cron only *proposes* — you still review and Apply.

## Project layout

```
config.py                 # symbol, parameter dataclasses, deployed params (REGIME_PARAMS, etc.)
bot.py                    # live loop: manage open position, check for new entry (60s)
DEPLOYMENT.md             # MT5 live-deployment guide (demo-first ladder)
strategies/
  base.py                 # Signal dataclass, BaseStrategy interface
  trend_following.py      # EMA-crossover (original Strategy A)
  london_breakout.py      # Asian-range breakout (original Strategy B)
  mean_reversion.py       # z-score / anchor fade scalper
  rsi_fade.py             # RSI-extreme fade scalper
  ml_classifier.py        # gradient-boosted TP-before-SL classifier
  trend_breakout.py       # Donchian / MA-momentum trend-follower
  regime_switch.py        # ★ regime-aware composite (deployed)
backtest/
  engine.py               # fast vectorized backtester (exec_tf=H1/M15) + slow reference
  regime.py               # trend/range classifier (ADX + EMA200 + efficiency ratio)
  walkforward.py          # rolling train→test WFO; stitched OOS + Monte Carlo
  montecarlo.py           # bootstrap robustness (CIs, skip test, slippage)
  campaign.py             # multi-family Optuna campaign (TRAIN/VAL/OOS)
  optimize.py / compare.py / walk_forward.py / iterate.py   # original pipeline
  ml_features.py          # backward-looking features + TP-before-SL labels
  metrics.py              # win rate, expectancy, PF, drawdown, Sharpe
  export_report.py        # exports results → report/data.json
  reoptimize.py           # auto re-optimize pipeline (download→optimize→WF→propose→apply)
  dashboard_server.py     # unified Control Center server (UI + control endpoints)
data/
  convert_dukascopy.py    # convert real Dukascopy CSVs → pipeline format
  generate_synthetic.py   # seeded synthetic GBM CSVs (pipeline testing only)
  download.py             # real MT5 bars (Windows only)
report/                   # unified dashboard UI (index.html + app.js + style.css + data.json), served by dashboard_server.py
indicators.py             # EMA, RSI, ATR, ADX (Wilder)
trade_manager.py          # break-even + ATR trailing SL — shared by bot.py and the backtester
risk_manager.py           # position sizing, drawdown guard (loss-streak pause, daily stop)
mt5_connector.py / executor.py   # MT5 connection, rates, order placement/modify/close
STRATEGY_LOG.md           # full experiment history: variants, OOS metrics, verdicts
```

## Backtest conventions

- Profits in price points (gold dollars on the per-trade profit curve).
- Spread applied to entry; SL checked before TP within the same bar (conservative fill).
- No look-ahead: `generate_signals` uses only data available at signal time (H4/H1 forward-filled onto lower timeframes); verified by the prefix test in `smoke_test.py`.
- Walk-forward: parameters are re-selected on each train window and evaluated only on the next (unseen) test window; all test segments are stitched into one OOS curve.

## Validation status

**The deployed strategy is validated on real Dukascopy data via walk-forward — but is NOT proven for live trading.** Per the project's honest-validation policy:

- Every decision metric comes from out-of-sample test windows the optimizer never selected on.
- **2025+ is no longer a clean holdout** (this design was informed by seeing it). The only true test is forward data.
- **Profit is tail-driven:** ~69% of the regime-switch's walk-forward profit came from a single 2026 trend window. Monte-Carlo worst-case (p5) PF is ~1.03 — real edge, but fragile.
- Synthetic data validates the *pipeline*, never a market edge.

## Live deployment (demo first)

Live trading requires **Windows + a running MT5 terminal**. `ACTIVE_STRATEGY` is set to `regime_switch` with `REGIME_PARAMS` optimized on the most recent 12 months. **Read `DEPLOYMENT.md` before risking anything** — it lays out the mandatory demo → micro-live → scale ladder, abort criteria, and how to re-derive parameters as markets drift.

## Risk controls (live)

- Position sized to risk `SHARED.risk_pct` of balance per trade (`risk_manager.calculate_lot`); drop to ≤ 0.5% before real money.
- Skip entries when spread exceeds `max_spread_points`.
- Pause 24h after N consecutive losses; halt for the day after the daily-loss cap.
- Break-even move then ATR trailing stop (`trade_manager.update_sl`) — the same code path used in backtests; regime_switch widens the trail so trends can run.
