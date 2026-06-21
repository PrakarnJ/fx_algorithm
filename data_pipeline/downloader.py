"""Download OHLC data from yfinance and write to stocks/{symbol}/{tf}.csv."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import pandas as pd

from algorithms.registry import TF_TO_YF, TF_TO_FILE
from config import STOCKS_DIR
from data_pipeline.resampler import resample_4h

logger = logging.getLogger(__name__)

# Max history period to request per yfinance interval
_PERIOD = {
    "1m": "7d",
    "2m": "60d",
    "5m": "60d",
    "15m": "60d",
    "30m": "60d",
    "60m": "730d",
    "1h": "730d",
    "90m": "60d",
    "1d": "max",
    "5d": "max",
    "1wk": "max",
    "1mo": "max",
    "3mo": "max",
}

# Minimum bars needed for a download to be considered useful
MIN_BARS = {
    "1m": 1000,
    "5m": 500,
    "15m": 500,
    "1h": 500,
    "4h": 200,
    "1d": 100,
    "1wk": 50,
    "1mo": 24,
}


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase columns, ensure UTC tz-aware DatetimeIndex, keep OHLC only."""
    df = df.rename(columns=str.lower)
    keep = [c for c in ("open", "high", "low", "close") if c in df.columns]
    df = df[keep].copy()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    df.index.name = "time"
    df = df.dropna()
    return df


def download(
    symbol: str,
    yf_ticker: str,
    internal_tfs: List[str],
    stocks_dir: Path = STOCKS_DIR,
    progress_callback=None,
) -> dict:
    """
    Download data for the given internal TF keys and write CSVs.

    Returns a dict of {internal_tf: row_count} for successfully downloaded TFs.
    """
    try:
        import yfinance as yf
    except ImportError:
        raise ImportError("Install yfinance: pip install yfinance")

    sym_dir = stocks_dir / symbol
    sym_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    need_h1 = "H4" in internal_tfs  # H4 is resampled from H1

    # Collect unique yfinance intervals to download (H4 → download 1h)
    yf_intervals: dict[str, str] = {}  # yf_interval → internal_tf (first match)
    for tf in internal_tfs:
        if tf == "H4":
            continue  # handled via resample
        yf_iv = TF_TO_YF.get(tf)
        if yf_iv and yf_iv not in yf_intervals:
            yf_intervals[yf_iv] = tf

    if need_h1 and "1h" not in yf_intervals:
        yf_intervals["1h"] = "H1"

    ticker = yf.Ticker(yf_ticker)
    total = len(yf_intervals) + (1 if need_h1 else 0)
    done = 0

    for yf_iv, primary_tf in yf_intervals.items():
        period = _PERIOD.get(yf_iv, "max")
        logger.info(f"[download] {symbol} {yf_iv} period={period}")
        try:
            df = ticker.history(period=period, interval=yf_iv, auto_adjust=True)
        except Exception as e:
            logger.error(f"[download] {symbol} {yf_iv} failed: {e}")
            done += 1
            if progress_callback:
                progress_callback(done, total, symbol, primary_tf, error=str(e))
            continue

        if df.empty:
            logger.warning(f"[download] {symbol} {yf_iv}: empty response")
            done += 1
            if progress_callback:
                progress_callback(done, total, symbol, primary_tf, error="empty response")
            continue

        df = _normalize(df)
        out_path = sym_dir / TF_TO_FILE[primary_tf]
        df.to_csv(out_path)
        results[primary_tf] = len(df)
        logger.info(f"[download] {symbol} {primary_tf}: {len(df)} bars → {out_path}")
        done += 1
        if progress_callback:
            progress_callback(done, total, symbol, primary_tf)

        # Immediately resample H1 → H4 if we just downloaded H1
        if yf_iv == "1h" and need_h1:
            h4_df = resample_4h(df)
            h4_path = sym_dir / TF_TO_FILE["H4"]
            h4_df.to_csv(h4_path)
            results["H4"] = len(h4_df)
            logger.info(f"[download] {symbol} H4 resampled: {len(h4_df)} bars → {h4_path}")
            done += 1
            if progress_callback:
                progress_callback(done, total, symbol, "H4")

    return results


def load_symbol_data(symbol: str, required_tfs: List[str], stocks_dir: Path = STOCKS_DIR) -> dict:
    """Load CSV files for a symbol into a dfs dict keyed by internal TF name."""
    sym_dir = stocks_dir / symbol
    dfs = {}
    for tf in required_tfs:
        fname = TF_TO_FILE.get(tf)
        if not fname:
            raise ValueError(f"Unknown TF key: {tf}")
        path = sym_dir / fname
        if not path.exists():
            raise FileNotFoundError(f"No data for {symbol}/{tf}: expected {path}")
        df = pd.read_csv(path, index_col="time", parse_dates=True)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        dfs[tf] = df
    return dfs
