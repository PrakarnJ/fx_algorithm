"""Resample H1 OHLC data to H4 (yfinance has no native 4h interval)."""
import pandas as pd


def resample_4h(h1_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate H1 bars into 4H sessions anchored at 00:00 UTC.
    Sessions: 00-04, 04-08, 08-12, 12-16, 16-20, 20-00 UTC.
    """
    df = h1_df.copy()
    resampled = df.resample("4h", origin="start_day").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
    ).dropna()
    resampled.index.name = "time"
    return resampled
