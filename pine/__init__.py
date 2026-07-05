"""Pine Script (TradingView) subset engine — lexer, parser, interpreter, strategy tester.

Accepts //@version=4, 5, or 6 (same core grammar across those releases).
//@version<4 (different builtin names, no ta.* namespace) and >6 are rejected
at compile time.

Supported subset:
  - indicator()/strategy()/study() declarations
  - variables: `x = expr`, `var x = expr` (persistent), typed decls, `x := expr`,
    `x += / -= expr`, tuple destructuring `[a, b, c] = ta.macd(...)`,
    historical access `x[n]`, list literals
  - if/else blocks, for i = a to b, ternary, and/or/not, arithmetic & comparisons
  - user-defined functions: `f(a, b) => expr` or an indented block
  - arrays: array.new_*/push/size/shift/pop/get/set/clear/avg/sum/min/max
  - ta.sma/ema/rma/rsi/atr/tr/stdev/highest/lowest/change/mom/crossover/
    crossunder/cross/macd/stoch/pivotlow/pivothigh
  - math.*, na()/nz(), input.*() (returns defval), time()/session filters
  - plot(), plotshape(), hline(), bgcolor() [accepted, not rendered]
  - strategy.entry (market/stop/limit, persists until filled/cancelled),
    strategy.close, strategy.close_all, strategy.cancel(_all),
    strategy.exit (stop/limit/loss/profit), strategy.position_size,
    strategy.position_avg_price, process_orders_on_close
  - single position (pyramiding = 1); opposite entry reverses

Anything outside the subset raises PineCompileError with line/col.
"""
from pine.errors import PineCompileError, PineRuntimeError
from pine.runner import compile_source, run

__all__ = ["compile_source", "run", "PineCompileError", "PineRuntimeError"]
