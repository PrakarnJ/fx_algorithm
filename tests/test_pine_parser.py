"""Lexer/parser: golden scripts compile, malformed scripts fail with position."""
import pytest

from pine import compile_source
from pine.errors import PineCompileError

GOLDEN = """
//@version=5
strategy("EMA Cross", overlay=true, initial_capital=50000)
fast = ta.ema(close, 9)
slow = ta.ema(close, 21)
plot(fast, "Fast", color.orange)
plot(slow, "Slow", color.blue)
if ta.crossover(fast, slow)
    strategy.entry("L", strategy.long)
if ta.crossunder(fast, slow)
    strategy.entry("S", strategy.short)
"""


def test_golden_script_compiles():
    prog = compile_source(GOLDEN)
    assert prog.script_type == "strategy"
    assert prog.title == "EMA Cross"
    assert prog.overlay is True
    assert prog.settings["initial_capital"] == 50000
    assert len(prog.body) == 6


def test_indicator_declaration():
    prog = compile_source('//@version=5\nindicator("My RSI", overlay=false)\nplot(ta.rsi(close, 14))')
    assert prog.script_type == "indicator"
    assert prog.overlay is False


def test_missing_declaration_rejected():
    with pytest.raises(PineCompileError) as e:
        compile_source("plot(close)")
    assert "indicator" in str(e.value)


def test_error_carries_position():
    # Trailing '+' invites line continuation, so the parser reports the
    # failure at the (empty) continuation point — line 3 or 4.
    with pytest.raises(PineCompileError) as e:
        compile_source('//@version=5\nindicator("x")\ny = close +')
    assert e.value.line in (3, 4)
    with pytest.raises(PineCompileError) as e2:
        compile_source('//@version=5\nindicator("x")\ny = close ! 2')
    assert e2.value.line == 3


def test_unsupported_features_rejected():
    for snippet, needle in [
        ('request.security(syminfo.tickerid, "D", close)', "security"),
        ("while close > 0\n    plot(close)", "while"),
        ("m = matrix.new(2, 2)", "matri"),
        ('l = line.new(0, 0, 1, 1)', "line"),
    ]:
        src = f'//@version=5\nindicator("x")\n{snippet}'
        with pytest.raises(PineCompileError) as e:
            compile_source(src)
        assert needle in str(e.value).lower()


def test_pyramiding_rejected():
    with pytest.raises(PineCompileError) as e:
        compile_source('//@version=5\nstrategy("x", pyramiding=5)\nplot(close)')
    assert "pyramiding" in str(e.value)


def test_if_requires_indented_block():
    with pytest.raises(PineCompileError):
        compile_source('//@version=5\nindicator("x")\nif close > 2\nplot(close)')


def test_multiline_call_continuation():
    prog = compile_source(
        '//@version=5\nindicator("x")\nplot(ta.ema(close,\n     20),\n     "EMA")'
    )
    assert len(prog.body) == 1


def test_tuple_destructuring_parses():
    prog = compile_source(
        '//@version=5\nindicator("x")\n[m, s, h] = ta.macd(close, 12, 26, 9)\nplot(m)'
    )
    assert len(prog.body) == 2


def test_else_if_chain():
    src = (
        '//@version=5\nstrategy("x")\n'
        "if close > open\n    strategy.entry(\"L\", strategy.long)\n"
        "else if close < open\n    strategy.entry(\"S\", strategy.short)\n"
        "else\n    strategy.close_all()"
    )
    prog = compile_source(src)
    assert len(prog.body) == 1
