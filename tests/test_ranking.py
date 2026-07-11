"""Ranking batch runner — per-script in-band failures, shared bars."""
from api.routers.ranking import run_ranking
from conftest import make_trend_bars

VALID_STRATEGY = """//@version=6
strategy("EMA Cross", overlay=true)
fast = ta.ema(close, 9)
slow = ta.ema(close, 21)
if ta.crossover(fast, slow)
    strategy.entry("L", strategy.long)
if ta.crossunder(fast, slow)
    strategy.entry("S", strategy.short)
"""

BROKEN_SOURCE = """//@version=6
strategy("Broken")
if ta.crossover(
"""

INDICATOR_SOURCE = """//@version=6
indicator("Just a plot")
plot(ta.ema(close, 9))
"""


def _scripts():
    return [
        {"id": 1, "name": "valid", "source": VALID_STRATEGY},
        {"id": 2, "name": "broken", "source": BROKEN_SOURCE},
        {"id": 3, "name": "indicator", "source": INDICATOR_SOURCE},
        {"id": 4, "name": "#4", "source": None},
    ]


def test_batch_never_raises_and_preserves_order():
    df = make_trend_bars(400)
    items = run_ranking(_scripts(), df, "H1")
    assert [it["script_id"] for it in items] == [1, 2, 3, 4]


def test_valid_strategy_produces_metrics():
    df = make_trend_bars(400)
    item = run_ranking(_scripts(), df, "H1")[0]
    assert item["ok"] is True
    assert item["error"] is None
    assert item["title"] == "EMA Cross"
    m = item["metrics"]
    assert m["total_trades"] > 0
    assert "net_profit" in m and "profit_factor" in m and "max_drawdown_pct" in m
    # Heavy fields must not leak into ranking items
    assert "bars" not in item and "plots" not in item and "equity" not in item


def test_compile_error_reported_in_band():
    df = make_trend_bars(400)
    item = run_ranking(_scripts(), df, "H1")[1]
    assert item["ok"] is False
    assert item["metrics"] is None
    assert item["error"].startswith("line ")


def test_indicator_script_rejected():
    df = make_trend_bars(400)
    item = run_ranking(_scripts(), df, "H1")[2]
    assert item["ok"] is False
    assert "indicator" in item["error"]


def test_missing_script_reported():
    df = make_trend_bars(400)
    item = run_ranking(_scripts(), df, "H1")[3]
    assert item["ok"] is False
    assert item["error"] == "script not found"
