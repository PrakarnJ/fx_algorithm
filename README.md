# XAUUSD Pine Studio

Paste a TradingView **Pine Script**, plot it on the **gold (XAUUSD)** chart, and backtest it — a single-instrument strategy studio with a TradingView-style Strategy Tester.

```
┌──────────────────────────────────────────────┐
│  React frontend  (Vite · Tailwind · CM6)      │  :5173 (dev) / :8000 (prod)
│  Pine editor · chart · Strategy Tester        │
└──────────────────┬───────────────────────────┘
                   │  HTTP
┌──────────────────▼───────────────────────────┐
│  FastAPI backend  (uvicorn · :8000)            │
│  /api/pine/validate  /api/pine/backtest        │
│  /api/chart/data     /api/chart/info           │
└──────────────────┬───────────────────────────┘
                   │
┌──────────────────▼───────────────────────────┐
│  pine/  — Pine Script subset engine           │
│  lexer → parser → bar-by-bar interpreter      │
│  → TV-style broker emulator → metrics         │
│                                               │
│  data/XAUUSD_{M15,H1,H4}.csv  (Dukascopy)     │
└──────────────────────────────────────────────┘
```

## Quick start

```bash
# 1. Backend (project virtualenv; system pip is externally managed)
python3 -m venv .venv                       # first time only
.venv/bin/pip install -r requirements.txt
.venv/bin/python3 -m uvicorn api.main:app --port 8000

# 2. Frontend (dev)
cd frontend && npm install && npm run dev   # → http://localhost:5173
# or production: npm run build, then FastAPI serves the SPA at :8000

# 3. Data — real Dukascopy gold bars, or synthetic for offline testing
.venv/bin/python3 data/generate_synthetic.py            # synthetic XAUUSD CSVs
npx dukascopy-node -i xauusd -from 2020-01-01 -to 2026-07-01 -t m15 -f csv -dir /tmp/duka
npx dukascopy-node -i xauusd -from 2020-01-01 -to 2026-07-01 -t h1  -f csv -dir /tmp/duka
npx dukascopy-node -i xauusd -from 2020-01-01 -to 2026-07-01 -t h4  -f csv -dir /tmp/duka
.venv/bin/python3 data/convert_dukascopy.py /tmp/duka   # → data/XAUUSD_{M15,H1,H4}.csv
```

Open the Studio, paste a script, press **Run** (⌘⏎). Strategy scripts get entry/exit markers on the chart plus a Strategy Tester panel (Overview / Equity Curve / List of Trades); indicator scripts just plot.

## Supported Pine subset (v4–v6 syntax)

`//@version=4`, `5`, or `6` are all accepted — the core grammar this engine implements (`ta.*` namespace, `var`, `strategy.*`, arrays, functions) is unchanged across those releases. `//@version=3` and earlier use different built-in names (no `ta.` prefix, `study()` only) and are rejected at compile time with a clear message; `//@version=7`+ is rejected as newer than this engine supports.

| Area | Supported |
|---|---|
| Declarations | `indicator()`, `strategy()` (title, overlay, initial_capital, default_qty_type/value, commission_type/value, process_orders_on_close) |
| Variables | `x = expr`, `var x = expr` (persistent), typed decls (`var float x`, `var array<float> a`), `x := expr`, `x += / -=`, `[a,b,c] = ta.macd(...)`, history `x[n]` |
| Control flow | `if` / `else if` / `else`, `for i = a to b`, ternary `? :`, `and` `or` `not` |
| Functions | user-defined `f(a, b) => expr` and indented-block bodies (last expression is the return value) |
| Arrays | `array.new_*`, `push`, `size`, `shift`, `pop`, `get`, `set`, `clear`, `avg`, `sum`, `min`, `max` |
| Series | `open high low close hl2 hlc3 ohlc4 volume bar_index time timeframe.period` |
| `ta.*` | `sma ema rma rsi atr tr stdev highest lowest change mom crossover crossunder cross macd stoch pivotlow pivothigh` |
| `math.*` | `abs sqrt log exp floor ceil sign max min round pow` |
| Time | `time("D")` day buckets, `time(timeframe.period, "HHMM-HHMM", "Asia/Bangkok")` session filters (zoneinfo timezones) |
| Misc | `na()`, `nz()`, `input.*()` (returns the default), `color.new()`, `str.tostring()` |
| Plotting | `plot` (line/histogram/linebr), `plotshape`, `hline`; `bgcolor`/`fill`/`alertcondition` accepted but not rendered |
| Strategy | `strategy.entry` (market/stop/limit — pending orders persist until filled or cancelled), `strategy.close(_all)`, `strategy.cancel(_all)`, `strategy.exit` (`stop`/`limit`/`loss`/`profit` in ticks), `strategy.position_size`, `strategy.position_avg_price`, `strategy.equity` |

**Not supported (clear compile error):** `request.security` / higher timeframes, `pyramiding > 1`, `while`/`switch`, matrices, drawing objects (`line.*`, `label.*`, `box.*`, `table.*`), methods/types.

See `examples/soldiers_sr_xauusd.pine` for a full real-world strategy (candlestick pattern + S/R pivot clustering + StochRSI + Fib SL/TP + session and daily-loss guards) that runs unmodified.

## Fill model (TradingView Strategy Tester emulation)

- Orders placed on bar *i* execute on bar *i+1*; market orders fill at the **next bar's open**.
- Stop/limit orders (entries and `strategy.exit`) fill intra-bar; when both a stop and a limit could fill in one bar, TV's documented path heuristic applies (open nearer high → open→high→low→close).
- Single position (pyramiding = 1); an opposite `strategy.entry` reverses.
- Commission charged per fill; sizing via `fixed` contracts, `percent_of_equity`, or `cash`.
- Metrics mirror TV's Overview: Net Profit, Profit Factor, Max Drawdown (on the mark-to-market equity curve), % Profitable, Avg Trade/Win/Loss, Open P&L.

> **Honesty note:** results are *close to but not identical to* TradingView's tester — TV uses tick-level bar magnification and broker-emulator details we do not replicate. And as always: never ship a strategy tuned until the backtest looks good — reserve an out-of-sample window for the decision metrics.

## Repository layout

```
pine/                 # Pine Script engine
  lexer.py            #   tokenizer (indentation-aware, line continuations)
  parser.py           #   recursive descent → AST (subset gate w/ line:col errors)
  interpreter.py      #   bar-by-bar series runtime, per-callsite ta state
  builtins.py         #   incremental ta.* implementations + constants
  tester.py           #   TV-style broker emulator + metrics
  runner.py           #   compile → run → JSON-ready result; data loader
api/                  # FastAPI: routers/pine.py, routers/chart.py, routers/logs.py
frontend/             # React SPA: PineStudioPage (CodeMirror editor · chart · tester)
data/                 # XAUUSD_{M15,H1,H4}.csv + synthetic generator + Dukascopy converter
indicators.py         # vectorized pandas TA (reference implementations for ta.*)
tests/                # pytest: parser, interpreter/ta parity, broker fills, indicators
```

## Tests

```bash
.venv/bin/python3 -m pytest tests/ -q
```

Covers: parser acceptance/rejection with error positions, interpreter semantics (`[n]`, `var`, crossover), `ta.*` parity against `indicators.py`, and broker-emulator fills (next-bar-open, SL/TP tick math, same-bar stop+limit path heuristic, reversal, commission, sizing) on hand-built bars with known outcomes.
