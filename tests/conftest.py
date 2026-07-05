import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd


def make_bars(n: int = 310, price: float = 2000.0, spread: float = 1.0, freq: str = "h") -> pd.DataFrame:
    """Flat OHLC bars: close = price, high = price+spread, low = price-spread."""
    idx = pd.date_range("2024-01-01", periods=n, freq=freq, tz="UTC")
    p = np.full(n, price)
    return pd.DataFrame(
        {"open": p, "high": p + spread, "low": p - spread, "close": p},
        index=idx,
    )


def make_trend_bars(n: int = 400, start: float = 2000.0, seed: int = 7) -> pd.DataFrame:
    """Noisy sine-wave bars — crossovers and reversals guaranteed."""
    rng = np.random.default_rng(seed)
    close = start + 30 * np.sin(np.arange(n) / 20) + rng.normal(0, 2, n).cumsum() * 0.1
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    high = np.maximum(open_, close) + 1.5
    low = np.minimum(open_, close) - 1.5
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=idx)


def make_custom_bars(rows: list[tuple]) -> pd.DataFrame:
    """Hand-built bars from (open, high, low, close) tuples — for exact-fill tests."""
    idx = pd.date_range("2024-01-01", periods=len(rows), freq="h", tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)
