"""Broker emulator: next-bar-open fills, SL/TP tick math, commission,
reversal, and TV-style metrics — all on hand-built bars with known outcomes."""
import pytest

from pine import compile_source, run
from tests.conftest import make_custom_bars


def run_strategy(body: str, df, decl_args: str = "") -> dict:
    src = f'//@version=5\nstrategy("t"{", " + decl_args if decl_args else ""})\n{body}'
    return run(compile_source(src), df)


def test_market_entry_fills_next_bar_open():
    #        open  high  low   close
    df = make_custom_bars([
        (100.0, 101.0, 99.0, 100.5),   # bar 0: signal fires here
        (102.0, 103.0, 101.0, 102.5),  # bar 1: must fill at open = 102
        (104.0, 105.0, 103.0, 104.5),
    ])
    res = run_strategy(
        "if bar_index == 0\n    strategy.entry(\"L\", strategy.long, qty=1)", df)
    assert len(res["trades"]) == 1
    t = res["trades"][0]
    assert t["entry_price"] == pytest.approx(102.0)   # bar 1 OPEN, not bar 0 close
    assert t["exit_reason"] == "end_of_data"
    assert t["exit_price"] == pytest.approx(104.5)    # final close
    assert t["profit"] == pytest.approx(2.5)


def test_exit_loss_profit_tick_math():
    # tick_size = 0.01 → loss=100 ticks = 1.00 below entry
    df = make_custom_bars([
        (100.0, 100.5, 99.5, 100.0),   # bar 0: entry signal
        (100.0, 100.4, 99.8, 100.2),   # bar 1: entry fills at 100.0
        (100.0, 100.5, 98.5, 98.8),    # bar 2: low 98.5 < stop 99.0 → stop fill
    ])
    res = run_strategy(
        "if bar_index == 0\n"
        "    strategy.entry(\"L\", strategy.long, qty=2)\n"
        "    strategy.exit(\"x\", from_entry=\"L\", loss=100, profit=500)", df)
    t = res["trades"][0]
    assert t["exit_reason"] == "stop"
    assert t["exit_price"] == pytest.approx(99.0)     # entry 100 − 100 ticks × 0.01
    assert t["profit"] == pytest.approx(-2.0)          # −1.00 × qty 2


def test_take_profit_limit_fill():
    df = make_custom_bars([
        (100.0, 100.5, 99.5, 100.0),
        (100.0, 100.4, 99.8, 100.2),   # entry at 100
        (100.2, 102.5, 100.0, 102.0),  # high 102.5 ≥ limit 102 → take profit
    ])
    res = run_strategy(
        "if bar_index == 0\n"
        "    strategy.entry(\"L\", strategy.long, qty=1)\n"
        "    strategy.exit(\"x\", from_entry=\"L\", profit=200)", df)
    t = res["trades"][0]
    assert t["exit_reason"] == "limit"
    assert t["exit_price"] == pytest.approx(102.0)
    assert t["profit"] == pytest.approx(2.0)


def test_stop_and_limit_same_bar_uses_path_heuristic():
    # Both stop (99) and limit (101) inside bar 2's range.
    # open 100.2 is nearer the high (100.9) than the low (98.5)
    # → up-first path → limit fills first.
    df = make_custom_bars([
        (100.0, 100.5, 99.5, 100.0),
        (100.0, 100.4, 99.8, 100.2),           # entry at 100
        (100.2, 100.9, 98.5, 99.0),            # h-o=0.7 < o-l=1.7 → up first... limit=101 > high
    ])
    # limit 101 is NOT reachable (high 100.9), stop 99 is → stop fills
    res = run_strategy(
        "if bar_index == 0\n"
        "    strategy.entry(\"L\", strategy.long, qty=1)\n"
        "    strategy.exit(\"x\", from_entry=\"L\", loss=100, profit=100)", df)
    t = res["trades"][0]
    assert t["exit_reason"] == "stop"

    # Now widen the bar so BOTH hit; open closer to high → limit first
    df2 = make_custom_bars([
        (100.0, 100.5, 99.5, 100.0),
        (100.0, 100.4, 99.8, 100.2),           # entry at 100
        (100.8, 101.2, 98.8, 99.5),            # h-o=0.4 < o-l=2.0 → up first → limit 101
    ])
    res2 = run_strategy(
        "if bar_index == 0\n"
        "    strategy.entry(\"L\", strategy.long, qty=1)\n"
        "    strategy.exit(\"x\", from_entry=\"L\", loss=100, profit=100)", df2)
    assert res2["trades"][0]["exit_reason"] == "limit"
    assert res2["trades"][0]["exit_price"] == pytest.approx(101.0)


def test_opposite_entry_reverses():
    df = make_custom_bars([
        (100.0, 100.5, 99.5, 100.0),   # long signal
        (101.0, 101.5, 100.5, 101.0),  # long fills at 101
        (102.0, 102.5, 101.5, 102.0),  # short signal (on this bar)
        (103.0, 103.5, 102.5, 103.0),  # reversal fills at 103
        (102.0, 102.5, 101.5, 102.0),
    ])
    res = run_strategy(
        "if bar_index == 0\n"
        "    strategy.entry(\"L\", strategy.long, qty=1)\n"
        "if bar_index == 2\n"
        "    strategy.entry(\"S\", strategy.short, qty=1)", df)
    assert len(res["trades"]) == 2
    first, second = res["trades"]
    assert first.get("direction") == "long"
    assert first["exit_reason"] == "reverse"
    assert first["exit_price"] == pytest.approx(103.0)
    assert first["profit"] == pytest.approx(2.0)
    assert second["direction"] == "short"
    assert second["entry_price"] == pytest.approx(103.0)


def test_commission_percent():
    # 1% commission on each fill: entry 100×1×1% = 1, exit 104.5×1×1% = 1.045
    df = make_custom_bars([
        (100.0, 100.5, 99.5, 100.0),
        (100.0, 100.5, 99.5, 100.0),   # entry at 100
        (104.0, 105.0, 103.5, 104.5),  # end of data → exit at 104.5
    ])
    res = run_strategy(
        "if bar_index == 0\n    strategy.entry(\"L\", strategy.long, qty=1)",
        df, decl_args="commission_type=strategy.commission.percent, commission_value=1")
    t = res["trades"][0]
    # serialized profit is rounded to cents
    assert t["profit"] == pytest.approx(4.5 - 1.0 - 1.045, abs=0.005)
    assert res["metrics"]["net_profit"] == pytest.approx(4.5 - 1.0 - 1.045, abs=0.01)


def test_position_size_gates_reentry():
    """`strategy.position_size == 0` must see the open position."""
    df = make_custom_bars([(100.0, 100.5, 99.5, 100.0)] * 10)
    res = run_strategy(
        "if strategy.position_size == 0\n"
        "    strategy.entry(\"L\", strategy.long, qty=1)", df)
    # One entry; flat bars → position never closes until end of data
    assert len(res["trades"]) == 1


def test_percent_of_equity_sizing():
    df = make_custom_bars([
        (100.0, 100.5, 99.5, 100.0),
        (100.0, 100.5, 99.5, 100.0),   # entry at 100
        (110.0, 110.5, 109.5, 110.0),
    ])
    res = run_strategy(
        "if bar_index == 0\n    strategy.entry(\"L\", strategy.long)", df,
        decl_args="initial_capital=10000, "
                  "default_qty_type=strategy.percent_of_equity, default_qty_value=50")
    t = res["trades"][0]
    assert t["qty"] == pytest.approx(50.0)             # 10000 × 50% / 100
    assert t["profit"] == pytest.approx(500.0)          # 10 pts × 50


def test_metrics_shape():
    df = make_custom_bars([
        (100.0, 100.5, 99.5, 100.0),
        (100.0, 100.5, 99.5, 100.0),
        (105.0, 105.5, 104.5, 105.0),
        (105.0, 105.5, 104.5, 105.0),
        (103.0, 103.5, 102.5, 103.0),
    ])
    res = run_strategy(
        "if bar_index == 0\n    strategy.entry(\"L\", strategy.long, qty=1)\n"
        "if bar_index == 2\n    strategy.close(\"L\")", df)
    m = res["metrics"]
    t = res["trades"][0]
    assert t["exit_reason"] == "close"
    assert t["exit_price"] == pytest.approx(105.0)     # next bar open after close()
    assert m["total_trades"] == 1
    assert m["net_profit"] == pytest.approx(5.0)
    assert m["percent_profitable"] == 100.0
    assert m["gross_loss"] == 0.0
    # equity curve: one value per bar, ends at initial + net
    assert len(res["equity"]) == len(df)
    assert res["equity"][-1] == pytest.approx(100000 + 5.0)


def test_indicator_script_has_no_tester():
    df = make_custom_bars([(100.0, 100.5, 99.5, 100.0)] * 5)
    src = '//@version=5\nindicator("i")\nplot(close)'
    res = run(compile_source(src), df)
    assert res["metrics"] is None
    assert res["trades"] == []
