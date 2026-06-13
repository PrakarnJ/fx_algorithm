"""
Market-regime classification — trend vs range.

Each bar is labelled trend_up / trend_down / range using three
backward-looking signals (no look-ahead):

  - ADX(n): trend *strength* (high = trending)
  - EMA(slow) direction: price above/below a long EMA → trend *direction*
  - Kaufman efficiency ratio: |net move| / sum|moves| over a window
    (near 1 = clean directional move, near 0 = choppy)

A bar is trending only when ADX and the efficiency ratio both clear their
thresholds; direction comes from the EMA. Everything else is range.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd

from indicators import adx, ema, atr


def efficiency_ratio(close: pd.Series, window: int) -> pd.Series:
    """Kaufman efficiency ratio in [0, 1]."""
    direction = (close - close.shift(window)).abs()
    volatility = close.diff().abs().rolling(window).sum()
    return (direction / volatility.replace(0, np.nan)).fillna(0.0)


def classify_regime(
    dfs: dict,
    tf: str,
    adx_period: int = 14,
    adx_trend: float = 25.0,
    ema_slow: int = 200,
    er_window: int = 20,
    er_trend: float = 0.30,
) -> pd.Series:
    """Return a Series (indexed like dfs[tf]) of 'trend_up'/'trend_down'/'range'.

    Regime is computed on H1 (the structural timeframe) and forward-filled
    onto the exec timeframe, so a fast M15/H1 strategy and the regime gate
    agree on the same higher-timeframe context.
    """
    h1 = dfs["H1"]
    adx_val = adx(h1["high"], h1["low"], h1["close"], adx_period)
    ema_val = ema(h1["close"], ema_slow)
    er_val = efficiency_ratio(h1["close"], er_window)

    trending = (adx_val >= adx_trend) & (er_val >= er_trend)
    up = h1["close"] > ema_val

    regime_h1 = pd.Series("range", index=h1.index)
    regime_h1[trending & up] = "trend_up"
    regime_h1[trending & ~up] = "trend_down"

    bars = dfs[tf]
    return regime_h1.reindex(bars.index, method="ffill").fillna("range")


def regime_fractions(regime: pd.Series) -> dict:
    """Share of bars in each regime — for reporting/attribution."""
    counts = regime.value_counts(normalize=True)
    return {k: round(float(counts.get(k, 0.0)), 3)
            for k in ("trend_up", "trend_down", "range")}
