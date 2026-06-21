"""Indicator formula correctness tests (no CSV data required)."""
import numpy as np
import pandas as pd
import pytest

from indicators import ema, rsi, atr, adx


# ── helpers ──────────────────────────────────────────────────────────────────

def _random_close(n=200, seed=0) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(np.cumsum(rng.standard_normal(n)) + 2000.0)


def _ohlc(close: pd.Series, spread: float = 1.0):
    high = close + spread
    low  = close - spread
    return high, low, close


# ── EMA ──────────────────────────────────────────────────────────────────────

def test_ema_matches_pandas_ewm():
    """Our EMA must equal pandas ewm(span, adjust=False)."""
    close = _random_close()
    period = 14
    expected = close.ewm(span=period, min_periods=period, adjust=False).mean()
    pd.testing.assert_series_equal(ema(close, period), expected)


def test_ema_constant_series():
    """EMA of a constant series converges to that constant."""
    close = pd.Series([100.0] * 60)
    result = ema(close, 10)
    assert abs(float(result.iloc[-1]) - 100.0) < 1e-8


def test_ema_warmup_nans():
    """EMA has NaN for the first (period-1) bars."""
    close = _random_close(50)
    period = 14
    result = ema(close, period)
    assert result.iloc[:period - 1].isna().all()
    assert result.iloc[period - 1:].notna().all()


# ── RSI ──────────────────────────────────────────────────────────────────────

def test_rsi_range():
    """RSI must be in [0, 100] for all valid bars."""
    close = _random_close()
    r = rsi(close, 14).dropna()
    assert (r >= 0).all() and (r <= 100).all()


def test_rsi_rising_series():
    """Monotonically rising prices → RSI should be high (> 70 after warmup)."""
    close = pd.Series(np.arange(1, 101, dtype=float))
    r = rsi(close, 14).dropna()
    assert float(r.iloc[-1]) > 70


def test_rsi_falling_series():
    """Monotonically falling prices → RSI should be low (< 30 after warmup)."""
    close = pd.Series(np.arange(100, 0, -1, dtype=float))
    r = rsi(close, 14).dropna()
    assert float(r.iloc[-1]) < 30


# ── ATR ──────────────────────────────────────────────────────────────────────

def test_atr_positive():
    """ATR must be strictly positive for all valid bars."""
    close = _random_close()
    high, low, _ = _ohlc(close)
    a = atr(high, low, close, 14).dropna()
    assert (a > 0).all()


def test_atr_flat_market():
    """ATR for a perfectly flat market (constant ±spread) converges to 2×spread."""
    n, spread = 100, 1.0
    close = pd.Series([100.0] * n)
    high  = pd.Series([100.0 + spread] * n)
    low   = pd.Series([100.0 - spread] * n)
    # True range each bar: max(H-L=2, |H-prev_C|=spread, |L-prev_C|=spread) = 2
    a = atr(high, low, close, 14)
    assert abs(float(a.iloc[-1]) - 2 * spread) < 0.01


def test_atr_increases_with_volatility():
    """Higher H-L spread → higher ATR."""
    n = 100
    close = pd.Series([100.0] * n)
    a_tight = atr(close + 0.5, close - 0.5, close, 14).iloc[-1]
    a_wide  = atr(close + 5.0, close - 5.0, close, 14).iloc[-1]
    assert a_wide > a_tight


# ── ADX ──────────────────────────────────────────────────────────────────────

def test_adx_range():
    """ADX must be in [0, 100] for all valid bars."""
    close = _random_close()
    high, low, _ = _ohlc(close)
    d = adx(high, low, close, 14).dropna()
    assert (d >= 0).all() and (d <= 100).all()


def test_adx_strong_trend():
    """A clean directional trend should produce ADX > 25."""
    close = pd.Series(np.linspace(1000, 2000, 200))
    high  = close + 2
    low   = close - 2
    d = adx(high, low, close, 14).dropna()
    assert float(d.iloc[-1]) > 25
