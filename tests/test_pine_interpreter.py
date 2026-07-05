"""Interpreter semantics: series vars, [n] history, `var` persistence,
and ta.* parity against the vectorized indicators.py reference."""
import numpy as np
import pandas as pd
import pytest

from indicators import atr as ref_atr, ema as ref_ema, rsi as ref_rsi
from pine import compile_source, run
from tests.conftest import make_trend_bars


def run_indicator(body: str, df: pd.DataFrame) -> dict:
    src = f'//@version=5\nindicator("t")\n{body}'
    return run(compile_source(src), df)


def plot_values(result: dict, idx: int = 0) -> list:
    return result["plots"][idx]["values"]


@pytest.fixture(scope="module")
def bars() -> pd.DataFrame:
    return make_trend_bars(400)


def test_ta_ema_matches_reference(bars):
    got = plot_values(run_indicator("plot(ta.ema(close, 20))", bars))
    want = ref_ema(bars["close"], 20)
    for g, w in zip(got, want):
        if g is None:
            assert np.isnan(w)
        else:
            assert g == pytest.approx(w, rel=1e-9)


def test_ta_rsi_matches_reference(bars):
    got = plot_values(run_indicator("plot(ta.rsi(close, 14))", bars))
    want = ref_rsi(bars["close"], 14)
    checked = 0
    for g, w in zip(got, want):
        if g is not None and not np.isnan(w):
            assert g == pytest.approx(w, rel=1e-6)
            checked += 1
    assert checked > 300


def test_ta_atr_matches_reference(bars):
    got = plot_values(run_indicator("plot(ta.atr(14))", bars))
    want = ref_atr(bars["high"], bars["low"], bars["close"], 14)
    checked = 0
    for g, w in zip(got, want):
        if g is not None and not np.isnan(w):
            assert g == pytest.approx(w, rel=1e-6)
            checked += 1
    assert checked > 300


def test_ta_sma_highest_lowest(bars):
    res = run_indicator(
        "plot(ta.sma(close, 10))\nplot(ta.highest(high, 5))\nplot(ta.lowest(low, 5))",
        bars)
    sma = plot_values(res, 0)
    hi = plot_values(res, 1)
    lo = plot_values(res, 2)
    closes = bars["close"].to_numpy()
    highs = bars["high"].to_numpy()
    lows = bars["low"].to_numpy()
    i = 100
    assert sma[i] == pytest.approx(closes[i - 9:i + 1].mean())
    assert hi[i] == pytest.approx(highs[i - 4:i + 1].max())
    assert lo[i] == pytest.approx(lows[i - 4:i + 1].min())


def test_historical_reference(bars):
    got = plot_values(run_indicator("plot(close[3])", bars))
    closes = bars["close"].to_numpy()
    assert got[0] is None and got[2] is None      # not enough history
    assert got[3] == pytest.approx(closes[0])
    assert got[100] == pytest.approx(closes[97])


def test_series_var_history(bars):
    """A derived variable's [1] is its previous-bar value."""
    got = plot_values(run_indicator("x = close * 2\nplot(x[1])", bars))
    closes = bars["close"].to_numpy()
    assert got[0] is None
    assert got[50] == pytest.approx(closes[49] * 2)


def test_var_persistence(bars):
    """`var` initializes once; := accumulates across bars."""
    got = plot_values(run_indicator(
        "var count = 0.0\nif close > open\n    count := count + 1\nplot(count)", bars))
    closes = bars["close"].to_numpy()
    opens = bars["open"].to_numpy()
    expected = np.cumsum(closes > opens)
    assert got[-1] == pytest.approx(float(expected[-1]))
    assert got[10] == pytest.approx(float(expected[10]))


def test_crossover_semantics():
    """crossover fires only on the crossing bar."""
    idx = pd.date_range("2024-01-01", periods=6, freq="h", tz="UTC")
    close = pd.Series([10.0, 10.0, 9.0, 11.0, 12.0, 11.5], index=idx)
    df = pd.DataFrame({"open": close, "high": close + 0.5,
                       "low": close - 0.5, "close": close}, index=idx)
    got = plot_values(run_indicator("c = ta.crossover(close, 10.5) ? 1 : 0\nplot(c)", df))
    assert got == [0, 0, 0, 1, 0, 0]


def test_ternary_and_nz(bars):
    got = plot_values(run_indicator("plot(nz(close[500], -1))", bars))
    assert got[0] == -1.0  # 500 bars back doesn't exist → nz default


def test_macd_tuple(bars):
    res = run_indicator("[m, s, h] = ta.macd(close, 12, 26, 9)\nplot(m)\nplot(s)\nplot(h)", bars)
    m = plot_values(res, 0)
    s = plot_values(res, 1)
    h = plot_values(res, 2)
    i = 200
    assert h[i] == pytest.approx(m[i] - s[i], rel=1e-9)


def test_plotshape_markers(bars):
    res = run_indicator(
        "up = ta.crossover(ta.ema(close, 5), ta.ema(close, 20))\n"
        "plotshape(up, style=shape.triangleup, location=location.belowbar, color=color.green, text=\"B\")",
        bars)
    assert len(res["shapes"]) > 0
    assert all(s["shape"] == "triangleup" for s in res["shapes"])


def test_input_returns_default(bars):
    got = plot_values(run_indicator("n = input.int(7, title=\"len\")\nplot(n)", bars))
    assert got[0] == 7.0
