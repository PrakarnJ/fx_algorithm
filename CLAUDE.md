# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

XAUUSD (Gold) algorithm development and backtesting platform. The current best strategy is `regime_switch` (composite Donchian trend + z-score mean-reversion router, walk-forward winner at PF 1.77 OOS on real data). The `algorithms/` folder contains the two original candidates (`trend_following`, `london_breakout`) plus exploratory strategies (`mean_reversion`, `rsi_fade`, `trend_breakout`, `ml_classifier`). The active strategy is selected by `ACTIVE_STRATEGY` in `config.py`.

## Commands

All Python runs use the project virtualenv (system pip is externally managed):

```bash
.venv/bin/python3 data/generate_synthetic.py    # generate synthetic CSVs for offline testing
.venv/bin/python3 backtest/compare.py           # head-to-head: optimize trend & breakout → walk-forward → winner (~3 min)
.venv/bin/python3 backtest/reoptimize.py        # auto re-optimize regime_switch on recent data → proposes data/regime_params.json
.venv/bin/python3 backtest/export_report.py     # re-run reproducible variants, export report/data.json, serve dashboard on :8765
.venv/bin/python3 backtest/dashboard_server.py  # Control Center web UI (Overview / Performance / Optimize / Deploy)
```

Smoke-test changes by importing modules and calling strategy `get_signal()`/`generate_signals()` with synthetic DataFrames (UTC-indexed OHLC), running `backtest/smoke_test.py`, or running `backtest/compare.py` end-to-end.

## Architecture

**Dual strategy interface.** Each strategy in `algorithms/` implements two entry points that must stay in sync:
- `get_signal(dfs) -> Signal | None` — incremental, used by the replay API on the latest bars.
- `generate_signals(dfs) -> DataFrame` — vectorized over all history, used by the fast backtest engine. ~100x faster than calling `get_signal` per bar.

`dfs` is a dict of UTC-indexed OHLC DataFrames keyed `"M15"`, `"H1"`, `"H4"`.

**Shared logic.** `trade_manager.update_sl()` (break-even + ATR trailing) is stateless and called from `backtest/engine.py`. Parameter dataclasses in `config.py` (`SharedParams`, `TrendFollowingParams`, `LondonBreakoutParams`, `RegimeSwitchParams`, plus the exploratory `MeanReversionParams`, `RsiFadeParams`, `TrendBreakoutParams`, `MLClassifierParams`) are constructed with candidate values by the optimizer and module-level defaults (`TREND_PARAMS`, `BREAKOUT_PARAMS`, `REGIME_PARAMS`, `SHARED`).

**Hot-patchable regime params.** If `data/regime_params.json` exists, `config.py` overlays its values onto `RegimeSwitchParams` at import time. `backtest/reoptimize.py` writes that file after a successful walk-forward, so re-optimized params take effect without editing source.

**Backtest pipeline** (`backtest/`):
- `compare.py` runs the original two-strategy bake-off — `optimize.py` grid-searches each strategy in-sample (≤ 2024-12-31), `walk_forward.py` evaluates the best parameters out-of-sample (≥ 2025-01-01) with an acceptance gate (PF ≥ 1.3, expectancy > 0, ≥ 30 trades), then `compare.py` recommends the winner.
- `engine.py` has two implementations: `run_backtest_fast()` (production path, uses `generate_signals`) and `run_backtest()` (slow rolling-slice reference for correctness checks, uses `get_signal`).
- `walkforward.py` (separate from `walk_forward.py`) does rolling train→test with stitched OOS equity and Monte-Carlo robustness bands (`montecarlo.py`).
- `regime.py` provides `classify_regime()` (ADX + Kaufman ER + EMA(200)) used by `regime_switch` and `trend_breakout`.
- `iterate.py` and `campaign.py` are exploratory runners for parameter sweeps (results land in `backtest/campaign_runs/`).
- `dashboard_server.py` and `export_report.py` power the Control Center web UI for monitoring and re-optimization.

**Backtest conventions:** profits are tracked in price points (1 point = $0.01 on XAUUSD), spread is applied to entry, and SL is checked before TP within the same bar (conservative fill assumption). No look-ahead: `generate_signals` implementations must only use data available at signal time (H4/H1 values are forward-filled onto lower timeframes).

**Honest-validation policy:** never tune until a backtest looks good and ship it — in-sample results are only for parameter selection; all reported/decision metrics come from the out-of-sample window. Synthetic data from `generate_synthetic.py` validates the pipeline only, not the strategy edge. The current `regime_switch` PF 1.77 is tail-driven; treat it as a backtested result only until forward-test data is available.
