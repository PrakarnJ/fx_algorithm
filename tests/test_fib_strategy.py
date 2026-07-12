"""Fib SL/TP ladder: BE at 0.236, SL→0.236 at 0.382, TP at 0.618 —
exact-fill assertions on hand-built bars, plus the real example script."""
from pathlib import Path

import pytest

from pine import compile_source, run
from tests.conftest import make_custom_bars, make_trend_bars

ROOT = Path(__file__).parent.parent
FIB_SCRIPTS = {
    "Breakout": (ROOT / "examples" / "fib_sl_tp_breakout_xauusd.pine").read_text(),
    "Reversal": (ROOT / "examples" / "fib_sl_tp_reversal_xauusd.pine").read_text(),
    "EMA Cross": (ROOT / "examples" / "fib_sl_tp_ema_cross_xauusd.pine").read_text(),
}


def test_fib_ladder_moves_stop_be_then_236():
    # Fixed fib range [100, 110]: lvl236=102.36, lvl382=103.82, tp=106.18.
    # Entry fills bar 1 @100; each SL move becomes active one bar later.
    df = make_custom_bars([
        (100.0, 100.5, 99.5, 100.0),   # bar 0: signal
        (100.0, 101.0, 99.6, 100.5),   # bar 1: entry fills @100 (exit rule queued)
        (100.5, 102.5, 100.2, 102.0),  # bar 2: touch 0.236 → SL to BE (active bar 3)
        (102.0, 104.0, 101.8, 103.9),  # bar 3: touch 0.382 → SL to 102.36 (active bar 4)
        (103.9, 106.5, 103.5, 106.0),  # bar 4: high ≥ 106.18 → TP limit fill
    ])
    src = (
        '//@version=5\n'
        'strategy("fib ladder")\n'
        'var float curSL = na\n'
        'var int stage = 0\n'
        'if bar_index == 0\n'
        '    strategy.entry("Long", strategy.long, qty=1)\n'
        'justOpened = strategy.position_size != 0 and strategy.position_size[1] == 0\n'
        'if justOpened\n'
        '    curSL := 99.0\n'
        '    stage := 0\n'
        'if strategy.position_size > 0\n'
        '    ep = strategy.position_avg_price\n'
        '    if stage < 1 and high >= 102.36\n'
        '        curSL := math.max(curSL, ep)\n'
        '        stage := 1\n'
        '    if stage < 2 and high >= 103.82\n'
        '        curSL := math.max(curSL, 102.36)\n'
        '        stage := 2\n'
        '    strategy.exit("XL", from_entry="Long", stop=curSL, limit=106.18)\n'
    )
    res = run(compile_source(src), df)

    t = res["trades"][0]
    assert t["exit_reason"] == "limit"
    assert t["exit_price"] == pytest.approx(106.18)
    assert t["profit"] == pytest.approx(6.18)

    lv = res["exit_levels"]
    # rule queued on bar 1 → live bar 2; each SL move lags its trigger by one bar
    assert lv["stop"] == [None, None, pytest.approx(99.0),
                          pytest.approx(100.0), pytest.approx(102.36)]
    assert lv["limit"] == [None, None] + [pytest.approx(106.18)] * 3


def spec_ladder(src: str) -> str:
    """Pin the Breakout script's ladder inputs to the original user spec
    (TP 0.618, BE at 0.236, lock 0.382→0.236, 0.5×ATR SL buffer) so the
    hand-built-bar fills below stay exact regardless of tuned defaults."""
    return (src
        .replace('input.string("Fib adaptive", "TP Mode"', 'input.string("Fib extension", "TP Mode"')
        .replace('input.float(6.0, "R:R ขั้นต่ำ', 'input.float(1.0, "R:R ขั้นต่ำ')
        .replace('input.float(1.618, "TP fib level"', 'input.float(0.618, "TP fib level"')
        .replace('input.float(0.5, "BE trigger fib"', 'input.float(0.236, "BE trigger fib"')
        .replace('input.float(1.0, "SL-lock trigger fib"', 'input.float(0.382, "SL-lock trigger fib"')
        .replace('input.float(0.618, "SL-lock target fib"', 'input.float(0.236, "SL-lock target fib"')
        .replace('input.float(1.0, "SL ATR buffer', 'input.float(0.5, "SL ATR buffer'))


def test_fib_script_breakout_full_trade_cycle():
    # Rally to 110, decline to 99.7, breakout bar 16 → long @ bar 17 open (100.9).
    # Fib [99.7, 110]: 0.236=102.1308, 0.382=103.6346, TP 0.618=106.0654.
    flat = [(100.0, 100.3, 99.7, 100.0)] * 10
    df = make_custom_bars(flat + [
        (100.0, 106.0, 100.0, 105.8),  # 10: rally starts
        (105.8, 110.0, 105.5, 109.5),  # 11: swing high 110 (pivot confirms bar 16)
        (109.5, 109.6, 104.0, 104.2),  # 12: decline
        (104.2, 104.5, 100.5, 100.8),  # 13
        (100.8, 101.2, 99.8, 100.0),   # 14: near the old low
        (100.0, 100.4, 99.9, 100.1),   # 15: inside bar at the low
        (100.1, 101.0, 100.0, 100.9),  # 16: breakout signal (close > high[15])
        (100.9, 101.5, 100.6, 101.2),  # 17: entry fills @100.9
        (101.2, 102.5, 101.0, 102.3),  # 18: touch 0.236 → BE+20pts (101.1)
        (102.3, 104.0, 102.0, 103.8),  # 19: touch 0.382 → SL to 102.1308
        (103.8, 106.6, 103.5, 106.2),  # 20: high ≥ 106.0654 → TP
    ])
    res = run(compile_source(spec_ladder(FIB_SCRIPTS["Breakout"])), df, timeframe="M15")

    assert len(res["trades"]) == 1
    t = res["trades"][0]
    assert t["direction"] == "long"
    assert t["entry_price"] == pytest.approx(100.9)
    assert t["exit_reason"] == "limit"
    assert t["exit_price"] == pytest.approx(106.0654)
    assert t["qty"] == pytest.approx(1.0)  # 0.01 lot = 1 oz

    lv = res["exit_levels"]
    # initial SL (swing − ATR buffer) live bar 18; BE bar 19; fib 0.236 bar 20
    assert lv["stop"][17] is None
    assert lv["stop"][18] is not None and lv["stop"][18] < 100.9
    assert lv["stop"][19] == pytest.approx(101.1)     # BE = entry + 20 points
    assert lv["stop"][20] == pytest.approx(102.1308)  # fib 0.236
    assert lv["limit"][18] == pytest.approx(106.0654)


def test_fib_script_fixed_pips_tp():
    # Same breakout scenario, TP Mode "Fixed pips" (default) with tpPips=40:
    # entry 100.9 → TP = 100.9 + 40 pips × $0.10 = 104.9;
    # BE trigger 50% (102.9), SL-lock trigger 75% (103.9) → lock to 50% (102.9).
    flat = [(100.0, 100.3, 99.7, 100.0)] * 10
    df = make_custom_bars(flat + [
        (100.0, 106.0, 100.0, 105.8),  # 10: rally
        (105.8, 110.0, 105.5, 109.5),  # 11: swing high 110
        (109.5, 109.6, 104.0, 104.2),  # 12: decline
        (104.2, 104.5, 100.5, 100.8),  # 13
        (100.8, 101.2, 99.8, 100.0),   # 14
        (100.0, 100.4, 99.9, 100.1),   # 15
        (100.1, 101.0, 100.0, 100.9),  # 16: breakout signal
        (100.9, 101.5, 100.6, 101.2),  # 17: entry fills @100.9
        (101.2, 102.5, 101.0, 102.3),  # 18: below BE trigger — no ladder move
        (102.3, 104.0, 102.0, 103.8),  # 19: ≥102.9 → BE, ≥103.9 → lock to 102.9
        (103.8, 106.6, 103.5, 106.2),  # 20: high ≥ 104.9 → TP
    ])
    src = (FIB_SCRIPTS["Breakout"]
           .replace('input.string("Fib adaptive", "TP Mode"',
                    'input.string("Fixed pips", "TP Mode"')
           .replace('input.float(6.0, "R:R ขั้นต่ำ', 'input.float(1.0, "R:R ขั้นต่ำ')
           .replace('input.float(100, "TP (pips', 'input.float(40, "TP (pips'))
    res = run(compile_source(src), df, timeframe="M15")

    assert len(res["trades"]) == 1
    t = res["trades"][0]
    assert t["exit_reason"] == "limit"
    assert t["exit_price"] == pytest.approx(104.9)   # entry + 40 pips
    assert t["profit"] == pytest.approx(4.0)          # 40 pips × $0.10 at qty 1

    lv = res["exit_levels"]
    assert lv["limit"][18] == pytest.approx(104.9)    # TP anchored to actual fill
    assert lv["stop"][20] == pytest.approx(102.9)     # locked at 50% of TP distance


def test_fib_script_adaptive_tp_picks_lowest_qualifying_extension():
    # Same breakout scenario, TP Mode "Fib adaptive" (default) with minRR=1.0:
    # reward at ext 1.236 (= 99.7 + 1.236×10.3 = 112.4308) already ≥ 1×risk,
    # so the lowest level is chosen. Price never reaches it → end_of_data exit.
    flat = [(100.0, 100.3, 99.7, 100.0)] * 10
    df = make_custom_bars(flat + [
        (100.0, 106.0, 100.0, 105.8),
        (105.8, 110.0, 105.5, 109.5),  # swing high 110
        (109.5, 109.6, 104.0, 104.2),
        (104.2, 104.5, 100.5, 100.8),
        (100.8, 101.2, 99.8, 100.0),
        (100.0, 100.4, 99.9, 100.1),
        (100.1, 101.0, 100.0, 100.9),  # breakout signal
        (100.9, 101.5, 100.6, 101.2),  # entry fills @100.9
        (101.2, 102.5, 101.0, 102.3),
        (102.3, 104.0, 102.0, 103.8),
        (103.8, 106.6, 103.5, 106.2),
    ])
    src = FIB_SCRIPTS["Breakout"].replace('input.float(6.0, "R:R ขั้นต่ำ',
                                          'input.float(1.0, "R:R ขั้นต่ำ')
    res = run(compile_source(src), df, timeframe="M15")

    assert len(res["trades"]) == 1
    assert res["trades"][0]["exit_reason"] == "end_of_data"
    assert res["exit_levels"]["limit"][18] == pytest.approx(112.4308)  # ext 1.236


def test_fib_script_all_entry_modes_run():
    df = make_trend_bars(600, seed=11)
    for src in FIB_SCRIPTS.values():
        res = run(compile_source(src), df, timeframe="M15")
        assert res["ok"] is True
        assert res["metrics"] is not None
        assert len(res["equity"]) == len(df)
        assert len(res["exit_levels"]["stop"]) == len(df)
