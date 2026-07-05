"""Bar-by-bar interpreter for the parsed Pine subset.

Execution model:
  for each bar i:
      broker.begin_bar(i)          # fills for orders placed on bar i-1
      execute every top-level statement (in order)
      broker.end_bar(i)            # process_orders_on_close fills + equity

Variables:
  - `x = expr` re-evaluates every bar; the per-bar values form a series so
    `x[1]` is yesterday's value.
  - `var x = expr` initializes on the first bar and carries forward.
  - `x := expr` mutates — resolved through the scope chain, so a nested
    if/for block can mutate an enclosing function local or a global.
  - Blocks (if/for/function bodies) create child scopes; `=` declares in the
    innermost scope, `:=` walks outward.

User functions (`f(a, b) => …`) run in a fresh scope with global (read-only)
fallback; the value of the last statement is the return value.

ta.* callsites keep incremental state keyed by AST uid (see builtins).
NOTE (same gotcha as TradingView): a ta.* call inside an `if` branch only
updates on bars where the branch runs.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

import numpy as np

from pine import ast_nodes as A
from pine import builtins as B
from pine.builtins import NAN, isna
from pine.errors import PineRuntimeError
from pine.tester import Broker

_MAX_HISTORY = 5000


class SeriesVar:
    """A global script variable — one value per bar."""
    __slots__ = ("values", "is_var")

    def __init__(self, is_var: bool):
        self.values: list = []
        self.is_var = is_var


class Scope:
    """Lexical block scope. `=` declares here; `:=` walks up the chain."""
    __slots__ = ("vars", "parent")

    def __init__(self, parent: Optional["Scope"]):
        self.vars: dict[str, Any] = {}
        self.parent = parent

    def get(self, name: str):
        s = self
        while s is not None:
            if name in s.vars:
                return True, s.vars[name]
            s = s.parent
        return False, None

    def reassign(self, name: str, value) -> bool:
        s = self
        while s is not None:
            if name in s.vars:
                s.vars[name] = value
                return True
            s = s.parent
        return False


class PlotCollector:
    def __init__(self):
        self.plots: dict[int, dict] = {}      # uid → {meta, values[]}
        self.shapes: list[dict] = []
        self.hlines: dict[int, dict] = {}
        self._palette_i = 0

    def next_color(self) -> str:
        c = B.PLOT_PALETTE[self._palette_i % len(B.PLOT_PALETTE)]
        self._palette_i += 1
        return c


class Interpreter:
    def __init__(self, program: A.Program, df, broker: Optional[Broker],
                 timeframe: str = "H1"):
        """`df` is a UTC-indexed OHLC DataFrame; `broker` is None for indicators."""
        self.program = program
        self.broker = broker
        self.timeframe = timeframe
        self.n = len(df)
        idx = df.index
        try:  # normalize to ns regardless of the index's storage unit (pandas 2.x)
            ns = idx.as_unit("ns").asi8
        except AttributeError:
            ns = idx.asi8
        self.times = (ns // 10**9).astype(np.int64)
        self.series = {
            "open": df["open"].to_numpy(dtype=float),
            "high": df["high"].to_numpy(dtype=float),
            "low": df["low"].to_numpy(dtype=float),
            "close": df["close"].to_numpy(dtype=float),
        }
        self.series["hl2"] = (self.series["high"] + self.series["low"]) / 2
        self.series["hlc3"] = (self.series["high"] + self.series["low"] + self.series["close"]) / 3
        self.series["ohlc4"] = (self.series["open"] + self.series["high"]
                                + self.series["low"] + self.series["close"]) / 4
        self.series["volume"] = (df["volume"].to_numpy(dtype=float)
                                 if "volume" in df.columns else np.zeros(self.n))

        self.globals: dict[str, SeriesVar] = {}
        self.scope: Optional[Scope] = None    # None at top level
        self.state: dict[int, Any] = {}       # AST uid → ta state / History
        self.collector = PlotCollector()
        self.bar = 0
        self._tz_cache: dict[str, ZoneInfo] = {}
        self._call_depth = 0

    # ── main loop ─────────────────────────────────────────────────────────────
    def run(self) -> None:
        for i in range(self.n):
            self.bar = i
            if self.broker is not None:
                self.broker.begin_bar(i)
            for stmt in self.program.body:
                self.exec_stmt(stmt)
            if self.broker is not None:
                self.broker.end_bar(i)
        if self.broker is not None and self.n:
            self.broker.finish(self.n - 1)

    # ── statements (each returns its value — Pine blocks are expressions) ────
    def exec_stmt(self, stmt) -> Any:
        if isinstance(stmt, A.Assign):
            return self.exec_assign(stmt)
        if isinstance(stmt, A.TupleAssign):
            return self.exec_tuple_assign(stmt)
        if isinstance(stmt, A.If):
            return self.exec_if(stmt)
        if isinstance(stmt, A.For):
            return self.exec_for(stmt)
        if isinstance(stmt, A.ExprStmt):
            return self.eval(stmt.expr)
        raise PineRuntimeError(f"unknown statement {type(stmt).__name__}",
                               stmt.line, stmt.col)

    def exec_assign(self, stmt: A.Assign) -> Any:
        if stmt.mode == "reassign":
            value = self.eval(stmt.expr)
            if self.scope is not None and self.scope.reassign(stmt.name, value):
                return value
            sv = self.globals.get(stmt.name)
            if sv is None or not sv.values:
                raise PineRuntimeError(f"cannot ':=' undeclared variable {stmt.name!r}",
                                       stmt.line, stmt.col)
            sv.values[-1] = value
            return value

        # Declarations inside blocks are scope-local
        if self.scope is not None:
            value = self.eval(stmt.expr)
            self.scope.vars[stmt.name] = value
            return value

        sv = self.globals.get(stmt.name)
        if sv is None:
            sv = SeriesVar(is_var=(stmt.mode == "var"))
            self.globals[stmt.name] = sv

        if sv.is_var and sv.values:
            # `var` — carry the previous bar's final value forward
            value = sv.values[-1]
        else:
            value = self.eval(stmt.expr)
        sv.values.append(value)
        if len(sv.values) > _MAX_HISTORY:
            del sv.values[: len(sv.values) - _MAX_HISTORY]
        return value

    def exec_tuple_assign(self, stmt: A.TupleAssign) -> Any:
        result = self.eval(stmt.call)
        if not isinstance(result, tuple):
            raise PineRuntimeError(
                f"{stmt.call.func}() does not return a tuple", stmt.line, stmt.col)
        if len(result) != len(stmt.names):
            raise PineRuntimeError(
                f"expected {len(stmt.names)} values, got {len(result)}",
                stmt.line, stmt.col)
        for name, value in zip(stmt.names, result):
            if self.scope is not None:
                self.scope.vars[name] = value
                continue
            sv = self.globals.get(name)
            if sv is None:
                sv = SeriesVar(is_var=False)
                self.globals[name] = sv
            sv.values.append(value)
            if len(sv.values) > _MAX_HISTORY:
                del sv.values[: len(sv.values) - _MAX_HISTORY]
        return result

    def exec_if(self, stmt: A.If) -> Any:
        cond = self.truthy(self.eval(stmt.cond))
        body = stmt.body if cond else stmt.orelse
        if not body:
            return NAN
        outer = self.scope
        self.scope = Scope(outer)
        try:
            value = NAN
            for s in body:
                value = self.exec_stmt(s)
            return value
        finally:
            self.scope = outer

    def exec_for(self, stmt: A.For) -> Any:
        start = self.eval(stmt.start)
        end = self.eval(stmt.end)
        if isna(start) or isna(end):
            return NAN
        start_i, end_i = int(start), int(end)
        step = 1 if end_i >= start_i else -1   # TV: counter moves toward `to`
        outer = self.scope
        self.scope = Scope(outer)
        try:
            value = NAN
            for i in range(start_i, end_i + step, step):
                self.scope.vars[stmt.var] = float(i)
                for s in stmt.body:
                    value = self.exec_stmt(s)
            return value
        finally:
            self.scope = outer

    def call_user_function(self, fn: A.FuncDef, args: list) -> Any:
        if len(args) != len(fn.params):
            raise PineRuntimeError(
                f"{fn.name}() expects {len(fn.params)} arguments, got {len(args)}",
                fn.line, fn.col)
        if self._call_depth > 32:
            raise PineRuntimeError(f"call depth exceeded in {fn.name}()", fn.line, fn.col)
        outer = self.scope
        # Fresh scope: function bodies see their params + globals, not caller locals
        self.scope = Scope(None)
        self.scope.vars.update(zip(fn.params, args))
        self._call_depth += 1
        try:
            value = NAN
            for s in fn.body:
                value = self.exec_stmt(s)
            return value
        finally:
            self._call_depth -= 1
            self.scope = outer

    # ── expression evaluation ────────────────────────────────────────────────
    def eval(self, node) -> Any:
        if isinstance(node, A.Num):
            return node.value
        if isinstance(node, A.Str):
            return node.value
        if isinstance(node, A.Bool):
            return node.value
        if isinstance(node, A.Na):
            return NAN
        if isinstance(node, A.ColorLit):
            return node.value
        if isinstance(node, A.ListLit):
            return [self.eval(item) for item in node.items]
        if isinstance(node, A.Ident):
            return self.lookup(node)
        if isinstance(node, A.HistRef):
            return self.eval_histref(node)
        if isinstance(node, A.UnaryOp):
            return self.eval_unary(node)
        if isinstance(node, A.BinOp):
            return self.eval_binop(node)
        if isinstance(node, A.Ternary):
            return (self.eval(node.then) if self.truthy(self.eval(node.cond))
                    else self.eval(node.other))
        if isinstance(node, A.Call):
            return self.eval_call(node)
        raise PineRuntimeError(f"cannot evaluate {type(node).__name__}",
                               node.line, node.col)

    def lookup(self, node: A.Ident) -> Any:
        name = node.name
        if self.scope is not None:
            found, value = self.scope.get(name)
            if found:
                return value
        sv = self.globals.get(name)
        if sv is not None:
            return sv.values[-1] if sv.values else NAN
        if name in self.series:
            return float(self.series[name][self.bar])
        if name == "bar_index":
            return float(self.bar)
        if name == "time":
            return float(self.times[self.bar]) * 1000.0  # Pine time is ms
        if name == "timeframe.period":
            return self.timeframe
        if name == "strategy.position_size":
            return self.broker.position_size if self.broker else 0.0
        if name == "strategy.position_avg_price":
            if self.broker and self.broker.position is not None:
                return self.broker.position.entry_price
            return NAN
        if name == "strategy.equity":
            return (self.broker.equity_at(float(self.series["close"][self.bar]))
                    if self.broker else NAN)
        if name == "strategy.opentrades":
            return 1.0 if (self.broker and self.broker.position) else 0.0
        if name == "strategy.closedtrades":
            return float(len(self.broker.closed)) if self.broker else 0.0
        if name == "syminfo.mintick":
            return self.broker.s.tick_size if self.broker else 0.01
        if name == "syminfo.pointvalue":
            return 1.0
        if name == "syminfo.tickerid" or name == "syminfo.ticker":
            return "XAUUSD"
        if name in B.CONSTANTS:
            return B.CONSTANTS[name]
        raise PineRuntimeError(f"unknown identifier {name!r}", node.line, node.col)

    def eval_histref(self, node: A.HistRef) -> Any:
        idx = self.eval(node.index)
        if isna(idx):
            return NAN
        n = int(idx)
        # Fast paths: builtin price series, script globals, broker series —
        # these read true per-bar history even if this expression is inside a
        # short-circuited branch.
        if isinstance(node.base, A.Ident):
            name = node.base.name
            if name in self.series:
                j = self.bar - n
                return float(self.series[name][j]) if j >= 0 else NAN
            if name == "strategy.position_size" and self.broker is not None:
                j = self.bar - n
                return self.broker.size_history[j] if j >= 0 else NAN
            # Only use the global fast path at top level; inside a function a
            # param may shadow the name.
            if self.scope is None or not self.scope.get(name)[0]:
                sv = self.globals.get(name)
                if sv is not None:
                    j = len(sv.values) - 1 - n
                    return sv.values[j] if j >= 0 else NAN
        # General path: keep a per-callsite history of the base expression.
        hist = self.state.get(node.uid)
        if hist is None:
            hist = B.History(maxlen=_MAX_HISTORY)
            self.state[node.uid] = hist
        hist.push(self.eval(node.base))
        return hist.back(n)

    def eval_unary(self, node: A.UnaryOp) -> Any:
        v = self.eval(node.operand)
        if node.op == "not":
            return not self.truthy(v)
        if node.op == "-":
            return NAN if isna(v) else -v
        return v

    def eval_binop(self, node: A.BinOp) -> Any:
        op = node.op
        if op == "and":
            return self.truthy(self.eval(node.left)) and self.truthy(self.eval(node.right))
        if op == "or":
            return self.truthy(self.eval(node.left)) or self.truthy(self.eval(node.right))

        a = self.eval(node.left)
        b = self.eval(node.right)
        if op in ("==", "!="):
            if isinstance(a, str) or isinstance(b, str):
                return (a == b) if op == "==" else (a != b)
        if op == "+" and (isinstance(a, str) or isinstance(b, str)):
            return f"{a}{b}"
        if isna(a) or isna(b):
            return NAN if op in ("+", "-", "*", "/", "%") else False
        try:
            if op == "+":
                return a + b
            if op == "-":
                return a - b
            if op == "*":
                return a * b
            if op == "/":
                return a / b if b != 0 else NAN
            if op == "%":
                return math.fmod(a, b) if b != 0 else NAN
            if op == "==":
                return a == b
            if op == "!=":
                return a != b
            if op == "<":
                return a < b
            if op == ">":
                return a > b
            if op == "<=":
                return a <= b
            if op == ">=":
                return a >= b
        except TypeError:
            raise PineRuntimeError(
                f"invalid operands for {op!r}: {type(a).__name__}, {type(b).__name__}",
                node.line, node.col)
        raise PineRuntimeError(f"unknown operator {op!r}", node.line, node.col)

    @staticmethod
    def truthy(v) -> bool:
        if isinstance(v, bool):
            return v
        if v is None:
            return False
        if isinstance(v, float):
            return not math.isnan(v) and v != 0.0
        return bool(v)

    # ── function calls ────────────────────────────────────────────────────────
    def eval_call(self, node: A.Call) -> Any:
        func = node.func

        if "." not in func and func in self.program.functions:
            args = [self.eval(a) for a in node.args]
            if node.kwargs:
                raise PineRuntimeError(
                    f"keyword arguments are not supported for user function {func}()",
                    node.line, node.col)
            return self.call_user_function(self.program.functions[func], args)

        if func.startswith("ta."):
            return self.eval_ta(node)
        if func.startswith("math."):
            return self.eval_math(node)
        if func.startswith("array."):
            return self.eval_array(node)
        if func.startswith("input"):
            return self.eval_input(node)
        if func.startswith("strategy."):
            return self.eval_strategy(node)
        if func == "plot":
            return self.eval_plot(node)
        if func == "plotshape" or func == "plotchar":
            return self.eval_plotshape(node)
        if func == "hline":
            return self.eval_hline(node)
        if func == "time":
            return self.eval_time(node)
        if func == "na":
            return isna(self._arg(node, 0, "x"))
        if func == "nz":
            v = self._arg(node, 0, "x")
            repl = self._arg(node, 1, "replacement", 0.0)
            return repl if isna(v) else v
        if func == "color.new":
            base = self._arg(node, 0, "color", "#787B86")
            transp = self._arg(node, 1, "transp", 0.0)
            return self._with_transparency(str(base), float(transp) if not isna(transp) else 0.0)
        if func in ("bgcolor", "barcolor", "alertcondition", "alert", "fill"):
            for a in node.args:
                self.eval(a)
            for v in node.kwargs.values():
                self.eval(v)
            return NAN  # accepted, not rendered
        if func in ("int", "float"):
            v = self._arg(node, 0, "x")
            return NAN if isna(v) else float(int(v)) if func == "int" else float(v)
        if func == "bool":
            return self.truthy(self._arg(node, 0, "x"))
        if func == "str.tostring":
            return str(self._arg(node, 0, "x"))

        raise PineRuntimeError(f"unsupported function {func}()", node.line, node.col)

    def _arg(self, node: A.Call, pos: int, name: str, default=None):
        if pos < len(node.args):
            return self.eval(node.args[pos])
        if name in node.kwargs:
            return self.eval(node.kwargs[name])
        return default

    def _const_int_arg(self, node: A.Call, pos: int, name: str, default=None) -> int:
        v = self._arg(node, pos, name, default)
        if v is None or isna(v):
            raise PineRuntimeError(f"{node.func}() requires {name}", node.line, node.col)
        return int(v)

    def _get_state(self, node: A.Call, factory):
        st = self.state.get(node.uid)
        if st is None:
            st = factory()
            self.state[node.uid] = st
        return st

    # ta.* — incremental per-callsite state
    def eval_ta(self, node: A.Call) -> Any:
        name = node.func[3:]

        if name in ("sma", "ema", "rma", "wma", "stdev", "highest", "lowest"):
            src = self._arg(node, 0, "source")
            period = self._const_int_arg(node, 1, "length")
            cls = {"sma": B.Sma, "ema": B.Ema, "rma": B.Rma, "wma": B.Sma,
                   "stdev": B.Stdev, "highest": B.Highest, "lowest": B.Lowest}[name]
            st = self._get_state(node, lambda: cls(period))
            return st.update(float(src) if not isna(src) else NAN)

        if name == "rsi":
            src = self._arg(node, 0, "source")
            period = self._const_int_arg(node, 1, "length")
            st = self._get_state(node, lambda: B.Rsi(period))
            return st.update(float(src) if not isna(src) else NAN)

        if name == "stoch":
            src = self._arg(node, 0, "source")
            hi = self._arg(node, 1, "high")
            lo = self._arg(node, 2, "low")
            period = self._const_int_arg(node, 3, "length")
            st = self._get_state(node, lambda: B.Stoch(period))
            return st.update(
                float(src) if not isna(src) else NAN,
                float(hi) if not isna(hi) else NAN,
                float(lo) if not isna(lo) else NAN)

        if name in ("pivotlow", "pivothigh"):
            # ta.pivotlow(source, left, right) or ta.pivotlow(left, right)
            if len(node.args) >= 3:
                src = self._arg(node, 0, "source")
                left = self._const_int_arg(node, 1, "leftbars")
                right = self._const_int_arg(node, 2, "rightbars")
            else:
                src = float(self.series["low" if name == "pivotlow" else "high"][self.bar])
                left = self._const_int_arg(node, 0, "leftbars")
                right = self._const_int_arg(node, 1, "rightbars")
            st = self._get_state(node, lambda: B.Pivot(left, right, name == "pivotlow"))
            return st.update(float(src) if not isna(src) else NAN)

        if name == "atr":
            period = self._const_int_arg(node, 0, "length")
            st = self._get_state(node, lambda: B.Atr(period))
            i = self.bar
            return st.update(float(self.series["high"][i]),
                             float(self.series["low"][i]),
                             float(self.series["close"][i]))

        if name == "tr":
            st = self._get_state(node, lambda: {"prev": NAN})
            i = self.bar
            v = B.true_range(float(self.series["high"][i]),
                             float(self.series["low"][i]), st["prev"])
            st["prev"] = float(self.series["close"][i])
            return v

        if name in ("change", "mom"):
            src = self._arg(node, 0, "source")
            n = self._const_int_arg(node, 1, "length", 1)
            hist = self._get_state(node, lambda: B.History(maxlen=max(n + 2, 10)))
            hist.push(src if not isna(src) else NAN)
            prev = hist.back(n)
            if isna(src) or isna(prev):
                return NAN
            return src - prev

        if name in ("crossover", "crossunder", "cross"):
            a = self._arg(node, 0, "source1")
            b = self._arg(node, 1, "source2")
            st = self._get_state(node, B.CrossState)
            mode = {"crossover": "over", "crossunder": "under", "cross": "any"}[name]
            return st.update(float(a) if not isna(a) else NAN,
                             float(b) if not isna(b) else NAN, mode)

        if name == "macd":
            src = self._arg(node, 0, "source")
            fast = self._const_int_arg(node, 1, "fastlen", 12)
            slow = self._const_int_arg(node, 2, "slowlen", 26)
            sig = self._const_int_arg(node, 3, "siglen", 9)
            st = self._get_state(node, lambda: B.Macd(fast, slow, sig))
            return st.update(float(src) if not isna(src) else NAN)

        raise PineRuntimeError(f"unsupported ta.{name}()", node.line, node.col)

    def eval_math(self, node: A.Call) -> Any:
        name = node.func[5:]
        one = {"abs": abs, "sqrt": math.sqrt, "log": math.log, "exp": math.exp,
               "floor": math.floor, "ceil": math.ceil, "sign": lambda x: (x > 0) - (x < 0)}
        if name in one:
            v = self._arg(node, 0, "x")
            if isna(v):
                return NAN
            try:
                return float(one[name](v))
            except ValueError:
                return NAN
        if name in ("max", "min"):
            vals = [self.eval(a) for a in node.args]
            vals = [v for v in vals if not isna(v)]
            if not vals:
                return NAN
            return float(max(vals) if name == "max" else min(vals))
        if name == "round":
            v = self._arg(node, 0, "x")
            nd = self._arg(node, 1, "precision", 0)
            if isna(v):
                return NAN
            return float(round(v, int(nd)))
        if name == "pow":
            a = self._arg(node, 0, "base")
            b = self._arg(node, 1, "exponent")
            if isna(a) or isna(b):
                return NAN
            return float(a ** b)
        raise PineRuntimeError(f"unsupported math.{name}()", node.line, node.col)

    def eval_array(self, node: A.Call) -> Any:
        """Pine arrays as plain Python lists."""
        name = node.func[6:]
        if name.startswith("new"):
            size = self._arg(node, 0, "size", 0)
            init = self._arg(node, 1, "initial_value", NAN)
            n = 0 if size is None or isna(size) else int(size)
            return [init] * n
        arr = self._arg(node, 0, "id")
        if not isinstance(arr, list):
            raise PineRuntimeError(f"array.{name}() requires an array", node.line, node.col)
        if name == "push":
            arr.append(self._arg(node, 1, "value"))
            return NAN
        if name == "size":
            return float(len(arr))
        if name == "shift":
            return arr.pop(0) if arr else NAN
        if name == "pop":
            return arr.pop() if arr else NAN
        if name == "get":
            i = int(self._arg(node, 1, "index"))
            if i < 0 or i >= len(arr):
                raise PineRuntimeError(f"array index {i} out of bounds (size {len(arr)})",
                                       node.line, node.col)
            return arr[i]
        if name == "set":
            i = int(self._arg(node, 1, "index"))
            if i < 0 or i >= len(arr):
                raise PineRuntimeError(f"array index {i} out of bounds (size {len(arr)})",
                                       node.line, node.col)
            arr[i] = self._arg(node, 2, "value")
            return NAN
        if name == "clear":
            arr.clear()
            return NAN
        if name in ("avg", "sum", "min", "max"):
            vals = [v for v in arr if not isna(v)]
            if not vals:
                return NAN
            if name == "avg":
                return sum(vals) / len(vals)
            return {"sum": sum, "min": min, "max": max}[name](vals)
        raise PineRuntimeError(f"unsupported array.{name}()", node.line, node.col)

    def eval_input(self, node: A.Call) -> Any:
        """input.*() returns its default value — no UI inputs in v1."""
        return self._arg(node, 0, "defval", NAN)

    # time() — session membership and higher-TF bucket open
    def eval_time(self, node: A.Call) -> Any:
        ts = int(self.times[self.bar])
        tf = self._arg(node, 0, "timeframe", None)
        session = self._arg(node, 1, "session", None)

        if session is None:
            # time("D") → open time (ms) of the current day bucket (UTC days)
            if isinstance(tf, str) and tf.upper() in ("D", "1D"):
                day_start = ts - ts % 86400
                return float(day_start) * 1000.0
            if isinstance(tf, str) and tf.upper() in ("W", "1W"):
                # Monday 00:00 UTC
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                week_start = ts - ((dt.weekday() * 86400) + dt.hour * 3600
                                   + dt.minute * 60 + dt.second)
                return float(week_start) * 1000.0
            return float(ts) * 1000.0  # chart timeframe → bar open time

        tz_name = self._arg(node, 2, "timezone", "UTC")
        tz = self._tz_cache.get(tz_name)
        if tz is None:
            try:
                tz = ZoneInfo(str(tz_name))
            except Exception:
                raise PineRuntimeError(f"unknown timezone {tz_name!r}", node.line, node.col)
            self._tz_cache[tz_name] = tz
        local = datetime.fromtimestamp(ts, tz=tz)
        minutes = local.hour * 60 + local.minute
        # session "1400-2300" (day-of-week suffix after ':' ignored)
        spec = str(session).split(":")[0]
        try:
            start_s, end_s = spec.split("-")
            start_m = int(start_s[:2]) * 60 + int(start_s[2:])
            end_m = int(end_s[:2]) * 60 + int(end_s[2:])
        except ValueError:
            raise PineRuntimeError(f"malformed session {session!r}", node.line, node.col)
        if start_m <= end_m:
            in_session = start_m <= minutes < end_m
        else:  # overnight session, e.g. 2200-0300
            in_session = minutes >= start_m or minutes < end_m
        return float(ts) * 1000.0 if in_session else NAN

    # plotting
    def eval_plot(self, node: A.Call) -> Any:
        value = self._arg(node, 0, "series")
        plot = self.collector.plots.get(node.uid)
        if plot is None:
            title = self._arg(node, 1, "title", f"Plot {len(self.collector.plots) + 1}")
            color = self._arg(node, 2, "color", None) or self.collector.next_color()
            style = node.kwargs.get("style")
            style_v = self.eval(style) if style is not None else "line"
            plot = {"title": str(title), "color": str(color),
                    "style": str(style_v), "values": [NAN] * self.bar}
            self.collector.plots[node.uid] = plot
        vals = plot["values"]
        # Pad if this plot() was skipped on earlier bars (inside an if)
        while len(vals) < self.bar:
            vals.append(NAN)
        ok = isinstance(value, (int, float)) and not isinstance(value, bool) and not isna(value)
        vals.append(float(value) if ok else NAN)
        return NAN

    def eval_plotshape(self, node: A.Call) -> Any:
        cond = self._arg(node, 0, "series")
        if not self.truthy(cond):
            return NAN
        kw = {k: self.eval(v) for k, v in node.kwargs.items()}
        self.collector.shapes.append({
            "time": int(self.times[self.bar]),
            "shape": str(kw.get("style", "circle")),
            "location": str(kw.get("location", "abovebar")),
            "color": str(kw.get("color", "#2962FF")),
            "text": str(kw.get("text", kw.get("char", ""))),
            "price": None,
        })
        return NAN

    def eval_hline(self, node: A.Call) -> Any:
        if node.uid in self.collector.hlines:
            return NAN
        price = self._arg(node, 0, "price")
        title = self._arg(node, 1, "title", "")
        color = self._arg(node, 2, "color", "#787B86")
        if not isna(price):
            self.collector.hlines[node.uid] = {
                "price": float(price), "title": str(title), "color": str(color)}
        return NAN

    # strategy.*
    def eval_strategy(self, node: A.Call) -> Any:
        if self.broker is None:
            raise PineRuntimeError(
                "strategy.*() requires a strategy() script", node.line, node.col)
        name = node.func[9:]

        if name == "entry":
            entry_id = self._arg(node, 0, "id")
            direction = self._arg(node, 1, "direction")
            if direction not in ("long", "short"):
                raise PineRuntimeError(
                    "direction must be strategy.long or strategy.short",
                    node.line, node.col)
            # TV positional order: id, direction, qty, limit, stop
            self.broker.entry(str(entry_id), direction,
                              qty=self._arg(node, 2, "qty", NAN),
                              limit=self._arg(node, 3, "limit", NAN),
                              stop=self._arg(node, 4, "stop", NAN))
            return NAN
        if name == "close":
            entry_id = self._arg(node, 0, "id", "*")
            self.broker.close(str(entry_id))
            return NAN
        if name == "close_all":
            self.broker.close("*")
            return NAN
        if name == "exit":
            self.broker.exit(
                from_entry=str(self._arg(node, 1, "from_entry", "")),
                stop=self._arg(node, 99, "stop", NAN),
                limit=self._arg(node, 99, "limit", NAN),
                loss=self._arg(node, 99, "loss", NAN),
                profit=self._arg(node, 99, "profit", NAN))
            return NAN
        if name == "cancel":
            entry_id = self._arg(node, 0, "id", None)
            self.broker.cancel(None if entry_id is None else str(entry_id))
            return NAN
        if name == "cancel_all":
            self.broker.cancel(None)
            return NAN

        raise PineRuntimeError(f"unsupported strategy.{name}()", node.line, node.col)

    @staticmethod
    def _with_transparency(color: str, transp: float) -> str:
        color = color if color.startswith("#") else "#787B86"
        alpha = max(0, min(255, round(255 * (1 - transp / 100.0))))
        return f"{color[:7]}{alpha:02X}"
