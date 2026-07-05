# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**XAUUSD Pine Studio** — paste a TradingView Pine Script, visualize it on the gold chart, and backtest it with a TradingView-style Strategy Tester. Single instrument (XAUUSD) by design; Pine Script is the only way to author a strategy.

## Commands

All Python runs use the project virtualenv (system pip is externally managed):

```bash
.venv/bin/python3 -m pytest tests/ -q                    # full test suite
.venv/bin/python3 -m uvicorn api.main:app --port 8000    # backend (serves built SPA too)
.venv/bin/python3 data/generate_synthetic.py             # synthetic XAUUSD CSVs for offline work
.venv/bin/python3 data/convert_dukascopy.py <dir>        # real Dukascopy bars → data/
cd frontend && npm run dev                               # frontend dev server on :5173
cd frontend && npm run build                             # typecheck + production build
```

Smoke-test engine changes without the server: `from pine import compile_source, run`, then `run(compile_source(src), df)` with a UTC-indexed OHLC DataFrame.

## Architecture

**Pipeline:** `pine/lexer.py` → `pine/parser.py` (AST, subset gate) → `pine/interpreter.py` (bar-by-bar) interleaved with `pine/tester.py` (broker emulator) → `pine/runner.py` (JSON-ready result) → `api/routers/pine.py` → `frontend/src/pages/PineStudioPage.tsx`.

- **Subset enforcement lives in the parser.** Unsupported Pine (request.security, while/switch, matrices, pyramiding>1, drawing objects) must raise `PineCompileError` with line/col — never silently ignore. Supported beyond the basics: user functions (`f(x) => …`), `for` loops, arrays, typed `var` declarations, `+=`, list literals, `time()` session filters.
- **Interpreter is bar-by-bar** with per-callsite `ta.*` state keyed by AST node uid (`pine/builtins.py`). `ta.*` warm-up matches `indicators.py` (pandas `ewm(adjust=False, min_periods=period)` semantics) — `tests/test_pine_interpreter.py` asserts parity; keep them in sync. Scoping is a chain (`Scope`): `=` declares in the innermost block, `:=`/`+=` walk outward — nested if/for mutation of function locals depends on this.
- **Broker emulator matches TradingView, not the old repo conventions:** orders placed on bar i fill on bar i+1 (market = next open); stop+limit in the same bar resolve by TV's open-nearer-high path heuristic; single position, opposite entry reverses. Exact-fill tests in `tests/test_pine_tester.py` use hand-built bars — extend those when touching fills.
- **Data:** `data/XAUUSD_{M15,H1,H4}.csv` is the single store (UTC-indexed `time,open,high,low,close`), loaded via `pine/runner.py:load_bars`. Timeframe map and XAUUSD cost defaults are in `config.py`.
- **Frontend:** `PineChart.tsx` renders the backtest response (candles, plot series, shape markers, trade markers, hlines); `StrategyTester.tsx` is the TV-style Overview/Equity/Trades panel. Editor is CodeMirror 6.

**Conventions:** tick size 0.01 ($0.01 = 1 point on XAUUSD); `strategy.exit` `loss`/`profit` are in ticks. Backtest results approximate TradingView but are not tick-identical (no bar magnifier) — say so when reporting numbers.

**Honest-validation policy:** never tune a script until the backtest looks good and call it done — reserve an out-of-sample window for decision metrics. Synthetic data validates the pipeline only, not a strategy edge.
