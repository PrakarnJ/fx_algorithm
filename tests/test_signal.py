"""Signal dataclass validation tests."""
import pandas as pd
import pytest

from algorithms.base import Signal

T = pd.Timestamp("2025-01-01", tz="UTC")


def test_valid_buy():
    s = Signal("buy", 2000.0, 1990.0, 2020.0, 5.0, T)
    assert s.direction == "buy"


def test_valid_sell():
    s = Signal("sell", 2000.0, 2010.0, 1980.0, 5.0, T)
    assert s.direction == "sell"


def test_bad_direction():
    with pytest.raises(ValueError, match="direction"):
        Signal("long", 2000.0, 1990.0, 2020.0, 5.0, T)


def test_buy_sl_above_entry():
    with pytest.raises(ValueError, match="sl"):
        Signal("buy", 2000.0, 2010.0, 2020.0, 5.0, T)


def test_buy_sl_equal_entry():
    with pytest.raises(ValueError, match="sl"):
        Signal("buy", 2000.0, 2000.0, 2020.0, 5.0, T)


def test_sell_sl_below_entry():
    with pytest.raises(ValueError, match="sl"):
        Signal("sell", 2000.0, 1990.0, 1980.0, 5.0, T)


def test_buy_tp_below_entry():
    with pytest.raises(ValueError, match="tp"):
        Signal("buy", 2000.0, 1990.0, 1980.0, 5.0, T)


def test_sell_tp_above_entry():
    with pytest.raises(ValueError, match="tp"):
        Signal("sell", 2000.0, 2010.0, 2020.0, 5.0, T)


def test_atr_zero_allowed():
    """atr=0 is valid (scalp mode: disables trailing stop)."""
    Signal("buy", 2000.0, 1990.0, 2020.0, 0.0, T)
