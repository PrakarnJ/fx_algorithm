"""
Feature and label engineering for the ML classifier strategy.

All features are strictly backward-looking (rolling/shift only) so the
prefix property holds: features for bar t computed on data truncated at t
equal those computed on the full series.

Labels look FORWARD (TP-before-SL within a horizon) and must only ever be
used at fit time, never inside generate_signals.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd

from indicators import rsi, atr

FEATURE_COLS = [
    "ret_1", "ret_4", "ret_16", "ret_64",
    "z_20", "z_60",
    "rsi_3", "rsi_14",
    "range_atr",
    "dist_mean_64",
    "hour_sin", "hour_cos", "dow",
]


def build_features(dfs: dict, tf: str) -> pd.DataFrame:
    bars = dfs[tf]
    h1 = dfs["H1"]
    close = bars["close"]

    out = pd.DataFrame(index=bars.index)
    for k in (1, 4, 16, 64):
        out[f"ret_{k}"] = close.pct_change(k)

    for L in (20, 60):
        mean = close.rolling(L).mean()
        std = close.rolling(L).std().replace(0, np.nan)
        out[f"z_{L}"] = (close - mean) / std

    out["rsi_3"] = rsi(close, 3)
    out["rsi_14"] = rsi(close, 14)

    atr_h1 = atr(h1["high"], h1["low"], h1["close"], 14).reindex(bars.index, method="ffill")
    out["range_atr"] = (bars["high"] - bars["low"]) / atr_h1.replace(0, np.nan)
    out["dist_mean_64"] = (close - close.rolling(64).mean()) / atr_h1.replace(0, np.nan)

    hours = bars.index.hour + bars.index.minute / 60.0
    out["hour_sin"] = np.sin(2 * np.pi * hours / 24)
    out["hour_cos"] = np.cos(2 * np.pi * hours / 24)
    out["dow"] = bars.index.dayofweek

    return out[FEATURE_COLS]


def build_labels(
    bars: pd.DataFrame,
    direction: str,
    tp_pts: float,
    sl_pts: float,
    horizon_bars: int,
) -> pd.Series:
    """1 if TP is touched strictly before SL within horizon_bars, else 0.
    Same-bar TP+SL touch counts as a loss (conservative, matches engine)."""
    close = bars["close"].values
    high = bars["high"].values
    low = bars["low"].values
    n = len(bars)

    if direction == "buy":
        tp_level = close + tp_pts
        sl_level = close - sl_pts
    else:
        tp_level = close - tp_pts
        sl_level = close + sl_pts

    labels = np.zeros(n, dtype=np.int8)
    h = horizon_bars
    # windows of future bars [i+1, i+h]
    for i in range(n - 1):
        end = min(i + 1 + h, n)
        w_high = high[i + 1:end]
        w_low = low[i + 1:end]
        if direction == "buy":
            tp_hits = np.flatnonzero(w_high >= tp_level[i])
            sl_hits = np.flatnonzero(w_low <= sl_level[i])
        else:
            tp_hits = np.flatnonzero(w_low <= tp_level[i])
            sl_hits = np.flatnonzero(w_high >= sl_level[i])
        if tp_hits.size == 0:
            continue
        if sl_hits.size == 0 or tp_hits[0] < sl_hits[0]:
            labels[i] = 1
    return pd.Series(labels, index=bars.index)
