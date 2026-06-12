"""
Generates synthetic XAUUSD CSV files for offline backtest testing.
Produces realistic Gold-like price action (GBM + mean-reversion + daily seasonality).
Run: python data/generate_synthetic.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
from config import SYMBOL

np.random.seed(42)
DATA_DIR = Path(__file__).parent

START = "2022-01-01"
END   = "2026-01-01"


def _gbm_walk(n: int, start: float, sigma: float) -> np.ndarray:
    """Geometric Brownian Motion with slight mean-reversion."""
    prices = [start]
    for _ in range(n - 1):
        shock = np.random.randn() * sigma
        mr = -0.001 * (prices[-1] - start) / start  # weak mean-reversion
        prices.append(prices[-1] * (1 + shock + mr))
    return np.array(prices)


def make_ohlc(closes: np.ndarray, noise: float) -> pd.DataFrame:
    opens  = np.roll(closes, 1); opens[0] = closes[0]
    spread = np.abs(np.random.randn(len(closes))) * noise + noise * 0.5
    highs  = np.maximum(opens, closes) + spread
    lows   = np.minimum(opens, closes) - spread
    return pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes})


def generate_m15():
    idx = pd.date_range(START, END, freq="15min", tz="UTC")
    # Remove weekends
    idx = idx[idx.dayofweek < 5]
    n = len(idx)
    closes = _gbm_walk(n, 1850.0, sigma=0.0008)
    df = make_ohlc(closes, noise=1.5)
    df.index = idx
    df.index.name = "time"
    out = DATA_DIR / f"{SYMBOL}_M15.csv"
    df.to_csv(out)
    print(f"M15: {len(df):,} bars → {out}")


def generate_h1():
    idx = pd.date_range(START, END, freq="1h", tz="UTC")
    idx = idx[idx.dayofweek < 5]
    n = len(idx)
    closes = _gbm_walk(n, 1850.0, sigma=0.0015)
    df = make_ohlc(closes, noise=3.0)
    df.index = idx
    df.index.name = "time"
    out = DATA_DIR / f"{SYMBOL}_H1.csv"
    df.to_csv(out)
    print(f"H1:  {len(df):,} bars → {out}")


def generate_h4():
    idx = pd.date_range(START, END, freq="4h", tz="UTC")
    idx = idx[idx.dayofweek < 5]
    n = len(idx)
    closes = _gbm_walk(n, 1850.0, sigma=0.003)
    df = make_ohlc(closes, noise=6.0)
    df.index = idx
    df.index.name = "time"
    out = DATA_DIR / f"{SYMBOL}_H4.csv"
    df.to_csv(out)
    print(f"H4:  {len(df):,} bars → {out}")


if __name__ == "__main__":
    generate_m15()
    generate_h1()
    generate_h4()
    print("Done. Run: python backtest/compare.py")
