import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest


def make_bars(n: int = 310, price: float = 2000.0, spread: float = 1.0, freq: str = "h") -> pd.DataFrame:
    """Flat OHLC bars: close = price, high = price+spread, low = price-spread."""
    idx = pd.date_range("2024-01-01", periods=n, freq=freq, tz="UTC")
    p = np.full(n, price)
    return pd.DataFrame(
        {"open": p, "high": p + spread, "low": p - spread, "close": p},
        index=idx,
    )


def make_dfs(n: int = 310, price: float = 2000.0) -> dict:
    """Minimal multi-TF dfs (all flat at price) for engine tests."""
    h1  = make_bars(n, price, freq="h")
    h4  = make_bars(n, price, freq="4h")
    m15 = make_bars(n * 4, price, freq="15min")
    return {"M15": m15, "H1": h1, "H4": h4}


class StubStrategy:
    """Strategy that emits a caller-supplied signals DataFrame."""
    exec_tf = "H1"

    def __init__(self, signals_df: pd.DataFrame, *, time_stop: int = 0,
                 full_close_at_partial: bool = False):
        self._signals = signals_df

        class _P:
            pass

        self.p = _P()
        self.p.time_stop_hours = time_stop
        self.p.full_close_at_partial = full_close_at_partial

    def generate_signals(self, dfs: dict) -> pd.DataFrame:
        return self._signals
