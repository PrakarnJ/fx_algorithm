# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Automated XAUUSD (Gold) trading bot for MetaTrader 5. The current live strategy is `regime_switch` (composite Donchian trend + z-score mean-reversion router, walk-forward winner at PF 1.77 OOS on real data — **demo only**, never forward-tested; see `DEPLOYMENT.md`). The `strategies/` folder also contains the two original candidates (`trend_following`, `london_breakout`) plus exploratory strategies (`mean_reversion`, `rsi_fade`, `trend_breakout`, `ml_classifier`) that have been backtested but are not wired into the live bot. The active strategy is selected by `ACTIVE_STRATEGY` in `config.py` — `bot.py` dispatches `"trend" | "breakout" | "regime_switch"`.

## Commands

All Python runs use the project virtualenv (system pip is externally managed):

```bash
.venv/bin/python3 data/generate_synthetic.py    # generate synthetic CSVs for offline testing
.venv/bin/python3 backtest/compare.py           # original head-to-head: optimize trend & breakout → walk-forward → winner (~3 min)
.venv/bin/python3 backtest/reoptimize.py        # auto re-optimize regime_switch on recent data → proposes data/regime_params.json
.venv/bin/python3 backtest/export_report.py     # re-run reproducible variants, export report/data.json, serve dashboard on :8765
.venv/bin/python3 backtest/dashboard_server.py  # Control Center web UI (Overview / Performance / Optimize / Deploy)
.venv/bin/python3 data/download.py              # download real bars from MT5 (requires running MT5 terminal — Windows/Wine only)
.venv/bin/python3 bot.py                        # live trading loop (requires MT5 terminal + MetaTrader5 package)
```

There is no test suite. Smoke-test changes by importing modules and calling strategy `get_signal()`/`generate_signals()` with synthetic DataFrames (UTC-indexed OHLC), running `backtest/smoke_test.py`, or running `backtest/compare.py` end-to-end.

**Platform caveat:** the `MetaTrader5` pip package only installs on Windows. On this Linux box, `bot.py`, `mt5_connector.py`, `executor.py`, and `data/download.py` cannot run — develop and backtest against CSVs in `data/` instead.

## Architecture

**Dual strategy interface.** Each strategy in `strategies/` implements two entry points that must stay in sync:
- `get_signal(dfs) -> Signal | None` — incremental, used by the live bot (`bot.py`) on the latest bars.
- `generate_signals(dfs) -> DataFrame` — vectorized over all history, used by the fast backtest engine. ~100x faster than calling `get_signal` per bar.

`dfs` is a dict of UTC-indexed OHLC DataFrames keyed `"M15"`, `"H1"`, `"H4"`.

**Shared logic between live and backtest.** `trade_manager.update_sl()` (break-even + ATR trailing) is stateless and called from both `bot.py` and `backtest/engine.py` — change it once, both paths follow. Parameter dataclasses in `config.py` (`SharedParams`, `TrendFollowingParams`, `LondonBreakoutParams`, `RegimeSwitchParams`, plus the exploratory `MeanReversionParams`, `RsiFadeParams`, `TrendBreakoutParams`, `MLClassifierParams`) are constructed with candidate values by the optimizer and module-level defaults (`TREND_PARAMS`, `BREAKOUT_PARAMS`, `REGIME_PARAMS`, `SHARED`) by the live bot. When `ACTIVE_STRATEGY == "regime_switch"`, `bot.py` overrides `SHARED.breakeven_atr_mult` and `trail_atr_mult` with the wider trend-leg values from `REGIME_PARAMS` so trends can run.

**Hot-patchable regime params.** If `data/regime_params.json` exists, `config.py` overlays its values onto `RegimeSwitchParams` at import time. `backtest/reoptimize.py` writes that file after a successful walk-forward, so re-optimized params can be deployed without editing source.

**Backtest pipeline** (`backtest/`):
- `compare.py` runs the original two-strategy bake-off — `optimize.py` grid-searches each strategy in-sample (≤ 2024-12-31), `walk_forward.py` evaluates the best parameters out-of-sample (≥ 2025-01-01) with an acceptance gate (PF ≥ 1.3, expectancy > 0, ≥ 30 trades), then `compare.py` recommends the winner.
- `engine.py` has two implementations: `run_backtest_fast()` (production path, uses `generate_signals`) and `run_backtest()` (slow rolling-slice reference for correctness checks, uses `get_signal`).
- `walkforward.py` (separate from `walk_forward.py`) does rolling train→test with stitched OOS equity and Monte-Carlo robustness bands (`montecarlo.py`).
- `regime.py` provides `classify_regime()` (ADX + Kaufman ER + EMA(200)) used by `regime_switch` and `trend_breakout`.
- `iterate.py` and `campaign.py` are exploratory runners for parameter sweeps (results land in `backtest/campaign_runs/`).
- `dashboard_server.py` and `export_report.py` power the Control Center web UI for monitoring, re-optimization, and deploying new params.

**Backtest conventions:** profits are tracked in price points (1 point = $0.01 on XAUUSD), spread is applied to entry, and SL is checked before TP within the same bar (conservative fill assumption). No look-ahead: `generate_signals` implementations must only use data available at signal time (H4/H1 values are forward-filled onto lower timeframes).

**Honest-validation policy** (carried from the original plan): never tune until a backtest looks good and ship it — in-sample results are only for parameter selection; all reported/decision metrics come from the out-of-sample window. Synthetic data from `generate_synthetic.py` validates the pipeline only, not the strategy edge. The current `regime_switch` PF 1.77 is tail-driven; treat it as demo-only until forward-test results justify a live-capital ramp per `DEPLOYMENT.md`.
