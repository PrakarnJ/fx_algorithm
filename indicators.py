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


def stoch_rsi(close: pd.Series, period: int = 14, k: int = 3, d: int = 3):
    """Stochastic RSI. Returns (K, D) as pd.Series on 0–100 scale."""
    rsi_vals = rsi(close, period)
    rsi_min = rsi_vals.rolling(period).min()
    rsi_max = rsi_vals.rolling(period).max()
    rng = (rsi_max - rsi_min).replace(0, np.finfo(float).eps)
    raw_k = (rsi_vals - rsi_min) / rng * 100
    K = raw_k.rolling(k).mean()
    D = K.rolling(d).mean()
    return K, D


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD. Returns (macd_line, signal_line, histogram) as pd.Series."""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line, macd_line - signal_line
