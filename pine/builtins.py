"""Incremental (bar-by-bar) implementations of Pine built-ins.

Each ta.* callsite in a script owns one state object, keyed by the AST node
uid, so `ta.ema(close, 20)` at two different places keeps independent state —
matching Pine's per-callsite series semantics.

Warm-up matches the repo's vectorized `indicators.py` (pandas
`min_periods=period`): functions return na until `period` inputs have been
seen; Wilder-family (rsi/atr) seed with the simple average of the first
`period` values, EMA seeds with the SMA of the first `period` values.
"""
from __future__ import annotations

import math
from collections import deque

NAN = float("nan")


def isna(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


# ── incremental indicator state ───────────────────────────────────────────────

class Sma:
    def __init__(self, period: int):
        self.period = period
        self.buf: deque = deque(maxlen=period)
        self.total = 0.0

    def update(self, x: float) -> float:
        if isna(x):
            return NAN
        if len(self.buf) == self.period:
            self.total -= self.buf[0]
        self.buf.append(x)
        self.total += x
        if len(self.buf) < self.period:
            return NAN
        return self.total / self.period


class _ExpSmooth:
    """Exponential smoothing matching pandas `ewm(adjust=False, min_periods=p)`:
    the recursion starts from the first input, output is na until `period`
    inputs have been seen."""

    def __init__(self, period: int, alpha: float):
        self.period = period
        self.alpha = alpha
        self.value = NAN
        self.count = 0

    def update(self, x: float) -> float:
        if isna(x):
            return self.value if self.count >= self.period else NAN
        if isna(self.value):
            self.value = x
        else:
            self.value = self.alpha * x + (1 - self.alpha) * self.value
        self.count += 1
        return self.value if self.count >= self.period else NAN


class Ema(_ExpSmooth):
    """EMA, alpha = 2/(period+1)."""

    def __init__(self, period: int):
        super().__init__(period, 2.0 / (period + 1.0))


class Rma(_ExpSmooth):
    """Wilder's smoothing, alpha = 1/period."""

    def __init__(self, period: int):
        super().__init__(period, 1.0 / period)


class Rsi:
    def __init__(self, period: int):
        self.avg_gain = Rma(period)
        self.avg_loss = Rma(period)
        self.prev = NAN

    def update(self, x: float) -> float:
        if isna(x):
            return NAN
        if isna(self.prev):
            self.prev = x
            return NAN
        delta = x - self.prev
        self.prev = x
        g = self.avg_gain.update(max(delta, 0.0))
        l = self.avg_loss.update(max(-delta, 0.0))
        if isna(g) or isna(l):
            return NAN
        if l == 0:
            return 100.0
        rs = g / l
        return 100.0 - 100.0 / (1.0 + rs)


class Atr:
    def __init__(self, period: int):
        self.rma = Rma(period)
        self.prev_close = NAN

    def update(self, high: float, low: float, close: float) -> float:
        tr = true_range(high, low, self.prev_close)
        self.prev_close = close
        return self.rma.update(tr)


def true_range(high: float, low: float, prev_close: float) -> float:
    if isna(prev_close):
        return high - low
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


class Stdev:
    def __init__(self, period: int):
        self.period = period
        self.buf: deque = deque(maxlen=period)

    def update(self, x: float) -> float:
        if isna(x):
            return NAN
        self.buf.append(x)
        if len(self.buf) < self.period:
            return NAN
        mean = sum(self.buf) / self.period
        var = sum((v - mean) ** 2 for v in self.buf) / self.period
        return math.sqrt(var)


class Highest:
    def __init__(self, period: int):
        self.period = period
        self.buf: deque = deque(maxlen=period)

    def update(self, x: float) -> float:
        if isna(x):
            return NAN
        self.buf.append(x)
        if len(self.buf) < self.period:
            return NAN
        return max(self.buf)


class Lowest:
    def __init__(self, period: int):
        self.period = period
        self.buf: deque = deque(maxlen=period)

    def update(self, x: float) -> float:
        if isna(x):
            return NAN
        self.buf.append(x)
        if len(self.buf) < self.period:
            return NAN
        return min(self.buf)


class Stoch:
    """Raw stochastic: 100 * (src - lowest(low, p)) / (highest(high, p) - lowest(low, p))."""

    def __init__(self, period: int):
        self.hi = Highest(period)
        self.lo = Lowest(period)

    def update(self, src: float, high: float, low: float) -> float:
        h = self.hi.update(high)
        l = self.lo.update(low)
        if isna(src) or isna(h) or isna(l):
            return NAN
        rng = h - l
        if rng == 0:
            return 0.0
        return 100.0 * (src - l) / rng


class Pivot:
    """ta.pivotlow/pivothigh — the value of the bar `right` bars ago when it is
    strictly beyond every other bar in the left+right window, else na."""

    def __init__(self, left: int, right: int, is_low: bool):
        self.left = left
        self.right = right
        self.is_low = is_low
        self.buf: deque = deque(maxlen=left + right + 1)

    def update(self, x: float) -> float:
        self.buf.append(x)
        if len(self.buf) < self.buf.maxlen:
            return NAN
        vals = list(self.buf)
        cand = vals[self.left]
        others = vals[: self.left] + vals[self.left + 1:]
        if any(isna(v) for v in vals):
            return NAN
        if self.is_low:
            return cand if all(cand < v for v in others) else NAN
        return cand if all(cand > v for v in others) else NAN


class History:
    """Rolling history for ta.change / ta.mom / expr[n] on computed values."""

    def __init__(self, maxlen: int = 500):
        self.buf: deque = deque(maxlen=maxlen)

    def push(self, x: float) -> None:
        self.buf.append(x)

    def back(self, n: int) -> float:
        idx = len(self.buf) - 1 - n
        if idx < 0:
            return NAN
        return self.buf[idx]


class CrossState:
    """crossover / crossunder / cross need the previous values of both series."""

    def __init__(self):
        self.prev_a = NAN
        self.prev_b = NAN

    def update(self, a: float, b: float, mode: str) -> bool:
        pa, pb = self.prev_a, self.prev_b
        self.prev_a, self.prev_b = a, b
        if isna(a) or isna(b) or isna(pa) or isna(pb):
            return False
        if mode == "over":
            return a > b and pa <= pb
        if mode == "under":
            return a < b and pa >= pb
        return (a > b and pa <= pb) or (a < b and pa >= pb)


class Macd:
    def __init__(self, fast: int, slow: int, signal: int):
        self.fast = Ema(fast)
        self.slow = Ema(slow)
        self.signal = Ema(signal)

    def update(self, x: float):
        f = self.fast.update(x)
        s = self.slow.update(x)
        if isna(f) or isna(s):
            return NAN, NAN, NAN
        line = f - s
        sig = self.signal.update(line)
        hist = NAN if isna(sig) else line - sig
        return line, sig, hist


# ── namespaced constants available to scripts ────────────────────────────────

COLOR_NAMES = {
    "color.red": "#F23645", "color.green": "#089981", "color.blue": "#2962FF",
    "color.orange": "#FF9800", "color.purple": "#9C27B0", "color.yellow": "#FDD835",
    "color.white": "#FFFFFF", "color.black": "#000000", "color.gray": "#787B86",
    "color.silver": "#B2B5BE", "color.teal": "#00897B", "color.aqua": "#00BCD4",
    "color.lime": "#00E676", "color.maroon": "#880E4F", "color.navy": "#311B92",
    "color.olive": "#808000", "color.fuchsia": "#E040FB",
}

CONSTANTS = {
    # strategy directions
    "strategy.long": "long",
    "strategy.short": "short",
    # qty types (declaration handles these as literals, but scripts may reference)
    "strategy.fixed": "fixed",
    "strategy.percent_of_equity": "percent_of_equity",
    "strategy.cash": "cash",
    "strategy.commission.percent": "percent",
    "strategy.commission.cash_per_contract": "cash_per_contract",
    "strategy.commission.cash_per_order": "cash_per_order",
    # plot styles
    "plot.style_line": "line",
    "plot.style_histogram": "histogram",
    "plot.style_circles": "circles",
    "plot.style_cross": "circles",
    "plot.style_stepline": "line",
    "plot.style_area": "line",
    "plot.style_columns": "histogram",
    "plot.style_linebr": "line",     # renderer already breaks lines at na gaps
    "plot.style_areabr": "line",
    # shapes
    "shape.triangleup": "triangleup",
    "shape.triangledown": "triangledown",
    "shape.arrowup": "arrowup",
    "shape.arrowdown": "arrowdown",
    "shape.circle": "circle",
    "shape.cross": "cross",
    "shape.xcross": "xcross",
    "shape.flag": "flag",
    "shape.square": "square",
    "shape.diamond": "diamond",
    "shape.labelup": "labelup",
    "shape.labeldown": "labeldown",
    # locations
    "location.abovebar": "abovebar",
    "location.belowbar": "belowbar",
    "location.absolute": "absolute",
    "location.top": "abovebar",
    "location.bottom": "belowbar",
    # sizes (accepted, rendering treats them alike)
    "size.tiny": "tiny", "size.small": "small", "size.normal": "normal",
    "size.large": "large", "size.huge": "huge", "size.auto": "auto",
    # line styles for hline (accepted)
    "hline.style_solid": "solid", "hline.style_dotted": "dotted",
    "hline.style_dashed": "dashed",
    # misc
    "barmerge.gaps_off": "gaps_off", "barmerge.gaps_on": "gaps_on",
    "display.all": "all", "display.none": "none",
}
CONSTANTS.update(COLOR_NAMES)

# Default plot palette when a script omits color= (TradingView-ish rotation)
PLOT_PALETTE = ["#2962FF", "#FF6D00", "#089981", "#F23645", "#9C27B0",
                "#FDD835", "#00BCD4", "#E040FB"]
