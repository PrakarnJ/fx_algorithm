import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, min_periods=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI (alpha = 1/period)."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.finfo(float).eps)
    return 100 - 100 / (1 + rs)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's ATR."""
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's ADX — measures trend strength (0–100; > 25 = trending)."""
    prev_high = high.shift(1)
    prev_low  = low.shift(1)

    plus_dm  = (high - prev_high).clip(lower=0)
    minus_dm = (prev_low - low).clip(lower=0)
    # Where the other DM is larger, zero out
    plus_dm  = plus_dm.where(plus_dm >= minus_dm, 0.0)
    minus_dm = minus_dm.where(minus_dm > plus_dm,  0.0)

    atr_vals    = atr(high, low, close, period)
    smooth_plus  = plus_dm.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    smooth_minus = minus_dm.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    plus_di  = 100 * smooth_plus  / atr_vals.replace(0, np.finfo(float).eps)
    minus_di = 100 * smooth_minus / atr_vals.replace(0, np.finfo(float).eps)

    di_sum = (plus_di + minus_di).replace(0, np.finfo(float).eps)
    dx     = 100 * (plus_di - minus_di).abs() / di_sum
    return dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
