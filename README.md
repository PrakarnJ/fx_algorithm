# XAUUSD Trading Bot

Automated XAUUSD (Gold) trading bot for MetaTrader 5. Two candidate strategies are validated head-to-head via in-sample optimization and walk-forward out-of-sample testing; the winner is selected by `ACTIVE_STRATEGY` in `config.py` and traded live by `bot.py`.

**Current winner: London Breakout** (62.5% OOS win rate, +6.31 pts expectancy/trade, profit factor 2.02 — on synthetic data; see [Validation status](#validation-status)).

## Strategies

| | Strategy A — Trend-Following | Strategy B — London Breakout |
|---|---|---|
| Idea | H1 EMA(9/21) crossover in the direction of the H4 EMA(50) trend, RSI(14) momentum filter | Break of the Asian-session (00:00–07:00 UTC) range during the London window, one trade per day |
| Stops | SL/TP as ATR multiples | SL at opposite side of range, TP as a multiple of range height |
| OOS verdict | ❌ Failed (negative expectancy) | ✅ Passed |

The deployed breakout configuration includes four enhancements kept after iterative validation (`backtest/iterate.py`): partial take-profit at 1R (close 50%, move SL to break-even), H1 EMA(50) trend filter, ADX(14) > 20 filter, and an 8-hour time stop. Full experiment history lives in `STRATEGY_LOG.md`.

Each strategy implements two entry points that must stay in sync:

- `get_signal(dfs)` — incremental, used by the live bot on the latest bars.
- `generate_signals(dfs)` — vectorized over all history, used by the fast backtest engine (~100× faster).

`dfs` is a dict of UTC-indexed OHLC DataFrames keyed `"M15"`, `"H1"`, `"H4"`.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install pandas numpy
```

The `MetaTrader5` package (in `requirements.txt`) only installs on **Windows** — it is required for live trading and real-data download, but not for backtesting. On macOS/Linux, develop and backtest against CSVs in `data/`.

Generate synthetic data for offline testing:

```bash
.venv/bin/python3 data/generate_synthetic.py
```

This writes `data/XAUUSD_{M15,H1,H4}.csv` (2022-01-01 → 2026-01-01, seeded GBM — deterministic across runs).

## Usage

```bash
.venv/bin/python3 backtest/compare.py    # full pipeline: optimize both strategies → walk-forward OOS → pick winner (~3 min)
.venv/bin/python3 backtest/iterate.py    # win-rate improvement ladder; appends results to STRATEGY_LOG.md
.venv/bin/python3 data/download.py       # download real bars from MT5 (Windows, running MT5 terminal)
.venv/bin/python3 bot.py                 # live trading loop (Windows, MT5 terminal logged in)
```

After running `compare.py`, set `ACTIVE_STRATEGY` in `config.py` to the recommended strategy (`'trend'` or `'breakout'`).

## Performance report (web dashboard)

A static dashboard visualizes backtest performance — equity curve + drawdown, monthly P&L, trade distribution, a sortable trade explorer, and an out-of-sample comparison of every variant ever tested.

```bash
.venv/bin/python3 backtest/export_report.py     # regenerate report/data.json from backtests
.venv/bin/python3 -m http.server 8765 -d report # serve the dashboard
# open http://localhost:8765
```

The exporter re-runs the four reproducible configurations (trend best-IS, breakout baseline, logged B-v4, deployed config) on both the OOS window (2025+) and full history. Charts use ECharts from a CDN; no build step required.

## Project layout

```
config.py                 # symbol, parameter dataclasses, deployed parameter values
bot.py                    # live loop: manage open position, check for new entry (60s interval)
strategies/
  base.py                 # Signal dataclass, BaseStrategy interface
  trend_following.py      # Strategy A
  london_breakout.py      # Strategy B
backtest/
  engine.py               # fast vectorized backtester + slow per-bar reference implementation
  optimize.py             # in-sample grid search (data ≤ 2024-12-31)
  walk_forward.py         # OOS evaluation (data ≥ 2025-01-01) with acceptance gate
  compare.py              # orchestrates optimize → walk-forward → decision
  iterate.py              # incremental enhancement ladder, logs to STRATEGY_LOG.md
  metrics.py              # win rate, expectancy, profit factor, drawdown, Sharpe
  export_report.py        # exports backtest results to report/data.json for the dashboard
data/
  generate_synthetic.py   # seeded synthetic GBM CSVs for offline testing
  download.py             # real MT5 bars (Windows only)
report/                   # static web dashboard (index.html + app.js + style.css + data.json)
indicators.py             # EMA, RSI, ATR, ADX (Wilder)
trade_manager.py          # break-even + ATR trailing SL — shared by bot.py and the backtester
risk_manager.py           # position sizing (1% risk), drawdown guard (loss streak pause, daily stop)
mt5_connector.py          # MT5 connection, rates, account/position queries
executor.py               # order placement (requote retry), SL modification, position close
STRATEGY_LOG.md           # experiment history: every variant tested, OOS metrics, verdicts
```

## Backtest conventions

- Profits are tracked in price points (1 point = $0.01 on XAUUSD).
- Spread is applied to the entry price; SL is checked before TP within the same bar (conservative fill assumption).
- No look-ahead: `generate_signals` implementations only use data available at signal time (H4/H1 values are forward-filled onto lower timeframes).
- Acceptance gate for OOS results: profit factor > 1.3, expectancy > 0, ≥ 30 trades.

## Validation status

**All recorded results are on synthetic GBM data.** They validate the pipeline, not the strategy edge. Per the project's honest-validation policy:

- In-sample results are used only for parameter selection; every reported or decision-driving metric comes from the out-of-sample window (2025-01-01+), which the optimizer never sees.
- Never tune until a backtest looks good and ship it.
- Before any live deployment, rerun `backtest/compare.py` on real bars from `data/download.py`, and verify the OOS gate still passes.

## Risk controls (live)

- 1% of balance risked per trade (`risk_manager.calculate_lot`).
- Skip entries when spread exceeds 50 points.
- Pause 24h after 3 consecutive losses; halt for the day after a 4% daily loss.
- Break-even move at 1×ATR profit, then ATR trailing stop (`trade_manager.update_sl` — the same code path used in backtests).
