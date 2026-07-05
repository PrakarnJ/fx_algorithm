"""Pine v2 subset: user functions, arrays, for loops, ta.stoch/pivots,
time()/session, broker pending-order persistence, process_orders_on_close."""
from pathlib import Path

import pandas as pd
import pytest

from pine import compile_source, run
from tests.conftest import make_custom_bars, make_trend_bars

ROOT = Path(__file__).parent.parent


def run_indicator(body: str, df) -> dict:
    return run(compile_source(f'//@version=5\nindicator("t")\n{body}'), df)


def run_strategy(body: str, df, decl_args: str = "") -> dict:
    src = f'//@version=5\nstrategy("t"{", " + decl_args if decl_args else ""})\n{body}'
    return run(compile_source(src), df)


def plot_values(res: dict, idx: int = 0) -> list:
    return res["plots"][idx]["values"]


# ── language features ────────────────────────────────────────────────────────

def test_inline_user_function():
    df = make_custom_bars([(100.0, 101.0, 99.0, 100.0)] * 3)
    got = plot_values(run_indicator("f(a, b) => a * 10 + b\nplot(f(2, 3))", df))
    assert got == [23.0, 23.0, 23.0]


def test_block_function_with_for_and_nested_mutation():
    """A nested if inside a for must mutate the function-local accumulator."""
    df = make_custom_bars([(100.0, 101.0, 99.0, 100.0)] * 2)
    body = (
        "sumEven(n) =>\n"
        "    s = 0\n"
        "    for i = 0 to n\n"
        "        if i % 2 == 0\n"
        "            s += i\n"
        "    s\n"
        "plot(sumEven(6))"
    )
    got = plot_values(run_indicator(body, df))
    assert got == [12.0, 12.0]  # 0+2+4+6


def test_function_reads_globals_not_caller_locals():
    df = make_custom_bars([(100.0, 101.0, 99.0, 100.0)] * 2)
    body = (
        "base = 100\n"
        "addBase(x) => x + base\n"
        "plot(addBase(5))"
    )
    assert plot_values(run_indicator(body, df))[0] == 105.0


def test_arrays_push_size_shift_get():
    df = make_custom_bars([(100.0, 101.0, 99.0, 100.0)] * 5)
    body = (
        "var array<float> a = array.new_float()\n"
        "array.push(a, close + bar_index)\n"
        "if array.size(a) > 3\n"
        "    array.shift(a)\n"
        "plot(array.size(a))\n"
        "plot(array.get(a, 0))"
    )
    res = run_indicator(body, df)
    sizes = plot_values(res, 0)
    first = plot_values(res, 1)
    assert sizes == [1.0, 2.0, 3.0, 3.0, 3.0]     # capped at 3 by shift
    assert first == [100.0, 100.0, 100.0, 101.0, 102.0]  # oldest shifts out


def test_typed_var_declarations():
    df = make_custom_bars([(100.0, 101.0, 99.0, 100.0)] * 3)
    body = (
        "var float x = na\n"
        "var int n = 0\n"
        "var bool flag = false\n"
        "if na(x)\n"
        "    x := close\n"
        "n := n + 1\n"
        "plot(x)\nplot(n)"
    )
    res = run_indicator(body, df)
    assert plot_values(res, 0) == [100.0, 100.0, 100.0]
    assert plot_values(res, 1) == [1.0, 2.0, 3.0]


def test_ta_stoch():
    """stoch(close,high,low,3) with rising closes → 100 when close == highest."""
    rows = [(1.0, 2.0, 0.0, 1.0), (2.0, 3.0, 1.0, 3.0), (3.0, 4.0, 2.0, 4.0)]
    df = make_custom_bars(rows)
    got = plot_values(run_indicator("plot(ta.stoch(close, high, low, 3))", df))
    assert got[0] is None and got[1] is None
    # window: highs [2,3,4] → 4, lows [0,1,2] → 0, close 4 → 100
    assert got[2] == pytest.approx(100.0)


def test_ta_pivotlow():
    lows = [5.0, 4.0, 2.0, 4.5, 5.5, 6.0, 6.5]
    rows = [(l + 1, l + 2, l, l + 1) for l in lows]
    df = make_custom_bars(rows)
    got = plot_values(run_indicator("plot(nz(ta.pivotlow(low, 2, 2), -1))", df))
    # pivot at index 2 (low=2.0) confirmed 2 bars later → reported at bar 4
    assert got[4] == pytest.approx(2.0)
    assert all(v == -1.0 for i, v in enumerate(got) if i != 4)


def test_time_session_filter():
    # H1 bars starting 2024-01-01 00:00 UTC; session 0700-0900 Asia/Bangkok = 0000-0200 UTC
    df = make_trend_bars(6)
    got = plot_values(run_indicator(
        'plot(na(time(timeframe.period, "0700-0900", "Asia/Bangkok")) ? 0 : 1)', df))
    assert got == [1.0, 1.0, 0.0, 0.0, 0.0, 0.0]


def test_time_day_change():
    idx = pd.date_range("2024-01-01 22:00", periods=4, freq="h", tz="UTC")
    df = pd.DataFrame({"open": [1.0] * 4, "high": [2.0] * 4,
                       "low": [0.5] * 4, "close": [1.5] * 4}, index=idx)
    got = plot_values(run_indicator('plot(ta.change(time("D")) != 0 ? 1 : 0)', df))
    # 22:00, 23:00, 00:00 (new day), 01:00
    assert got == [0.0, 0.0, 1.0, 0.0]


# ── broker upgrades ──────────────────────────────────────────────────────────

def test_pending_limit_order_persists_and_fills():
    df = make_custom_bars([
        (100.0, 100.5, 99.5, 100.0),   # bar 0: place limit buy @ 98
        (100.0, 100.5, 99.5, 100.0),   # bar 1: not reached — stays pending
        (100.0, 100.5, 99.5, 100.0),   # bar 2: not reached
        (99.0, 99.5, 97.5, 98.5),      # bar 3: low 97.5 ≤ 98 → fills @ 98
        (99.0, 99.5, 98.5, 99.0),
    ])
    res = run_strategy(
        "if bar_index == 0\n    strategy.entry(\"L\", strategy.long, qty=1, limit=98)", df)
    assert len(res["trades"]) == 1
    assert res["trades"][0]["entry_price"] == pytest.approx(98.0)
    assert res["trades"][0]["entry_time"] == res["bars"][3]["time"]


def test_cancel_pending_order():
    df = make_custom_bars([
        (100.0, 100.5, 99.5, 100.0),   # bar 0: place limit buy @ 98
        (100.0, 100.5, 99.5, 100.0),   # bar 1: cancel it
        (97.0, 97.5, 96.5, 97.0),      # bar 2: would have filled — must not
        (97.0, 97.5, 96.5, 97.0),
    ])
    res = run_strategy(
        "if bar_index == 0\n    strategy.entry(\"L\", strategy.long, qty=1, limit=98)\n"
        "if bar_index == 1\n    strategy.cancel(\"L\")", df)
    assert res["trades"] == []


def test_process_orders_on_close_fills_same_bar():
    df = make_custom_bars([
        (100.0, 100.5, 99.5, 101.0),   # bar 0: signal → fills at THIS close (101)
        (102.0, 102.5, 101.5, 102.0),
        (103.0, 103.5, 102.5, 103.0),
    ])
    res = run_strategy(
        "if bar_index == 0\n    strategy.entry(\"L\", strategy.long, qty=1)",
        df, decl_args="process_orders_on_close=true")
    t = res["trades"][0]
    assert t["entry_price"] == pytest.approx(101.0)   # same-bar close, not next open
    assert t["entry_time"] == res["bars"][0]["time"]


def test_position_size_history_survives_short_circuit():
    """`x and strategy.position_size[1] == 0` must read true history even on
    bars where the left side short-circuits."""
    df = make_custom_bars([(100.0, 100.5, 99.5, 100.0)] * 6)
    body = (
        "if bar_index == 0\n    strategy.entry(\"L\", strategy.long, qty=1)\n"
        "justOpened = strategy.position_size != 0 and strategy.position_size[1] == 0\n"
        "plot(justOpened ? 1 : 0)"
    )
    got = plot_values(run_strategy(body, df))
    # entry fills at bar 1 open → justOpened true exactly once, at bar 1
    assert got == [0.0, 1.0, 0.0, 0.0, 0.0, 0.0]


def test_position_avg_price():
    df = make_custom_bars([
        (100.0, 100.5, 99.5, 100.0),
        (102.0, 102.5, 101.5, 102.0),  # entry fills at 102
        (103.0, 103.5, 102.5, 103.0),
    ])
    got = plot_values(run_strategy(
        "if bar_index == 0\n    strategy.entry(\"L\", strategy.long, qty=1)\n"
        "plot(nz(strategy.position_avg_price, -1))", df))
    assert got == [-1.0, 102.0, 102.0]


# ── the real-world script ────────────────────────────────────────────────────

def test_soldiers_example_script_compiles_and_runs():
    src = (ROOT / "examples" / "soldiers_sr_xauusd.pine").read_text()
    prog = compile_source(src)
    assert prog.script_type == "strategy"
    assert set(prog.functions) == {"countTouches", "nearSRZone", "bodyPctOK",
                                   "openInPrevBody", "fibL", "fibS"}
    df = make_trend_bars(600, seed=11)
    res = run(prog, df, timeframe="M15")
    assert res["ok"] is True
    assert res["metrics"] is not None
    assert len(res["equity"]) == len(df)
    # 3 conditional plots (entry/tp/sl) always registered
    assert len(res["plots"]) == 3
