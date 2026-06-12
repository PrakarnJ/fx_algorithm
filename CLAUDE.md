# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Automated XAUUSD (Gold) trading bot for MetaTrader 5. Two candidate strategies (trend-following EMA crossover, London breakout) are validated head-to-head via walk-forward backtesting; the winner is selected by `ACTIVE_STRATEGY` in `config.py`.

## Commands

All Python runs use the project virtualenv (system pip is externally managed):

```bash
.venv/bin/python3 data/generate_synthetic.py   # generate synthetic CSVs for offline testing
.venv/bin/python3 backtest/compare.py          # full pipeline: optimize both strategies → walk-forward OOS → pick winner (~3 min)
.venv/bin/python3 data/download.py             # download real bars from MT5 (requires running MT5 terminal — Windows/Wine only)
.venv/bin/python3 bot.py                       # live trading loop (requires MT5 terminal + MetaTrader5 package)
```

There is no test suite. Smoke-test changes by importing modules and calling strategy `get_signal()`/`generate_signals()` with synthetic DataFrames (UTC-indexed OHLC), or by running `backtest/compare.py` end-to-end.

**Platform caveat:** the `MetaTrader5` pip package only installs on Windows. On this Linux box, `bot.py`, `mt5_connector.py`, `executor.py`, and `data/download.py` cannot run — develop and backtest against CSVs in `data/` instead.

## Architecture

**Dual strategy interface.** Each strategy in `strategies/` implements two entry points that must stay in sync:
- `get_signal(dfs) -> Signal | None` — incremental, used by the live bot (`bot.py`) on the latest bars.
- `generate_signals(dfs) -> DataFrame` — vectorized over all history, used by the fast backtest engine. ~100x faster than calling `get_signal` per bar.

`dfs` is a dict of UTC-indexed OHLC DataFrames keyed `"M15"`, `"H1"`, `"H4"`.

**Shared logic between live and backtest.** `trade_manager.update_sl()` (break-even + ATR trailing) is stateless and called from both `bot.py` and `backtest/engine.py` — change it once, both paths follow. Same with parameter dataclasses in `config.py`: the optimizer constructs them with candidate values, the live bot uses the module-level defaults (`TREND_PARAMS`, `BREAKOUT_PARAMS`, `SHARED`).

**Backtest pipeline** (`backtest/`): `compare.py` orchestrates everything — `optimize.py` grid-searches each strategy in-sample (≤ 2024-12-31), `walk_forward.py` evaluates the best parameters out-of-sample (≥ 2025-01-01) with an acceptance gate (PF > 1.3, expectancy > 0, ≥ 30 trades), then `compare.py` recommends the winner. `engine.py` has two implementations: `run_backtest_fast()` (production path, uses `generate_signals`) and `run_backtest()` (slow rolling-slice reference for correctness checks, uses `get_signal`).

**Backtest conventions:** profits are tracked in price points (1 point = $0.01 on XAUUSD), spread is applied to entry, and SL is checked before TP within the same bar (conservative fill assumption). No look-ahead: `generate_signals` implementations must only use data available at signal time (H4/H1 values are forward-filled onto lower timeframes).

**Honest-validation policy** (carried from the original plan): never tune until a backtest looks good and ship it — in-sample results are only for parameter selection; all reported/decision metrics come from the out-of-sample window. Synthetic data from `generate_synthetic.py` validates the pipeline only, not the strategy edge.
