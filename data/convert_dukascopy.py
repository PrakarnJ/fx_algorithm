"""
Convert dukascopy-node CSV exports into the pipeline's data format.

Input:  CSVs downloaded via
        npx dukascopy-node -i xauusd -from 2022-01-01 -to <today> -t {m15,h1,h4} -f csv
Output: data/XAUUSD_{M15,H1,H4}.csv  (UTC time index, open/high/low/close)

Cleanup applied:
  - millisecond timestamps → UTC datetime index
  - weekend bars dropped
  - flat padded bars dropped (Dukascopy fills non-trading periods with
    zero-range bars where open == high == low == close)

Run: python data/convert_dukascopy.py <input_dir>
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import SYMBOL

DATA_DIR = Path(__file__).parent
TF_MAP = {"m15": "M15", "h1": "H1", "h4": "H4"}


def convert(sources: list, tf_out: str) -> pd.DataFrame:
    parts = []
    for src in sources:
        df = pd.read_csv(src)
        df["time"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        parts.append(df.set_index("time")[["open", "high", "low", "close"]])
    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated(keep="last")]

    n_raw = len(df)
    df = df[df.index.dayofweek < 5]                       # weekends
    df = df[~((df["high"] == df["low"]) & (df["open"] == df["close"]))]  # padded flat bars

    out = DATA_DIR / f"{SYMBOL}_{tf_out}.csv"
    df.to_csv(out)
    print(f"{tf_out}: {n_raw:,} raw → {len(df):,} bars "
          f"({df.index[0]:%Y-%m-%d} → {df.index[-1]:%Y-%m-%d})  "
          f"close range {df['close'].min():.0f}–{df['close'].max():.0f}  → {out.name}")
    return df


def main(input_dir: str) -> None:
    src_dir = Path(input_dir)
    for tf_in, tf_out in TF_MAP.items():
        matches = sorted(src_dir.glob(f"xauusd-{tf_in}-*.csv"))
        if not matches:
            print(f"WARNING: no file for {tf_in} in {src_dir}")
            continue
        convert(matches, tf_out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/duka")
