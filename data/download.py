"""
Download historical XAUUSD bars from a running MT5 terminal and save to CSV.
Run from the forex_algorithm/ directory:  python data/download.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import MetaTrader5 as mt5
import pandas as pd
import mt5_connector as conn
from config import SYMBOL, TF_M15, TF_H1, TF_H4

DATA_DIR = Path(__file__).parent
MAX_BARS = 200_000  # request as many bars as the broker holds


def download(symbol: str, timeframe: int, tf_name: str) -> None:
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, MAX_BARS)
    if rates is None:
        print(f"[ERROR] No data for {tf_name}: {mt5.last_error()}")
        return
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    out = DATA_DIR / f"{symbol}_{tf_name}.csv"
    df.to_csv(out)
    print(f"[OK] {tf_name}: {len(df):,} bars  {df.index[0]} → {df.index[-1]}  → {out}")


if __name__ == "__main__":
    conn.connect()
    download(SYMBOL, TF_M15, "M15")
    download(SYMBOL, TF_H1,  "H1")
    download(SYMBOL, TF_H4,  "H4")
    conn.disconnect()
