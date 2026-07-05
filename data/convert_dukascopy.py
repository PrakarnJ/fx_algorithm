"""
Convert dukascopy-node CSV exports into the platform data store.

DOWNLOAD (requires Node.js):
  npm install -g dukascopy-node        # one-time install
  npx dukascopy-node -i xauusd -from 2020-01-01 -to 2026-01-01 -t m15 -f csv
  npx dukascopy-node -i xauusd -from 2020-01-01 -to 2026-01-01 -t h1  -f csv
  npx dukascopy-node -i xauusd -from 2020-01-01 -to 2026-01-01 -t h4  -f csv

Then run:
  .venv/bin/python3 data/convert_dukascopy.py <directory_with_csv_files>

Output: data/XAUUSD_{M15,H1,H4}.csv — merged with any existing bars so
re-running only fills gaps and extends the history.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATA_DIR, TF_TO_FILE

# Dukascopy TF name → internal file name inside data/
TF_MAP = {
    "m15": TF_TO_FILE["M15"],
    "h1":  TF_TO_FILE["H1"],
    "h4":  TF_TO_FILE["H4"],
}


def _load_dukascopy_csv(path: Path) -> pd.DataFrame:
    """Parse a dukascopy-node CSV file into a UTC-indexed OHLC DataFrame."""
    df = pd.read_csv(path)
    df["time"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("time")[["open", "high", "low", "close"]]
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]
    # Drop weekends
    df = df[df.index.dayofweek < 5]
    # Drop padded flat bars (Dukascopy fills non-trading periods with zero-range bars)
    df = df[~((df["high"] == df["low"]) & (df["open"] == df["close"]))]
    return df


def convert(sources: list[Path], out_filename: str) -> None:
    parts = [_load_dukascopy_csv(p) for p in sources]
    duka_df = pd.concat(parts).sort_index()
    duka_df = duka_df[~duka_df.index.duplicated(keep="last")]

    out_path = DATA_DIR / out_filename
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Merge with existing bars so re-runs extend rather than clobber history
    if out_path.exists():
        existing = pd.read_csv(out_path, index_col="time", parse_dates=True)
        if existing.index.tz is None:
            existing.index = existing.index.tz_localize("UTC")
        else:
            existing.index = existing.index.tz_convert("UTC")
        merged = pd.concat([duka_df, existing])
        # Keep the existing bar when timestamps overlap
        merged = merged[~merged.index.duplicated(keep="last")].sort_index()
        print(f"  Merged {len(duka_df):,} Dukascopy bars + {len(existing):,} existing → {len(merged):,} bars")
    else:
        merged = duka_df
        print(f"  {len(merged):,} bars (no existing file to merge)")

    merged.to_csv(out_path)
    print(f"  {out_filename}: {merged.index.min().date()} → {merged.index.max().date()}  "
          f"close {merged['close'].min():.0f}–{merged['close'].max():.0f}")


def main(input_dir: str) -> None:
    src_dir = Path(input_dir)
    print(f"Reading Dukascopy CSVs from: {src_dir.resolve()}")
    print(f"Writing to: {DATA_DIR.resolve()}\n")

    found_any = False
    for tf_in, out_filename in TF_MAP.items():
        matches = sorted(src_dir.glob(f"xauusd-{tf_in}-*.csv"))
        if not matches:
            print(f"  WARNING: no file matching xauusd-{tf_in}-*.csv in {src_dir}")
            continue
        print(f"[{tf_in}] {len(matches)} file(s):")
        convert(matches, out_filename)
        print()
        found_any = True

    if not found_any:
        print("No Dukascopy CSV files found. Download them first:")
        print("  npm install -g dukascopy-node")
        print(f"  npx dukascopy-node -i xauusd -from 2020-01-01 -to $(date +%Y-%m-%d) -t m15 -f csv")
        print(f"  npx dukascopy-node -i xauusd -from 2020-01-01 -to $(date +%Y-%m-%d) -t h1  -f csv")
        print(f"  npx dukascopy-node -i xauusd -from 2020-01-01 -to $(date +%Y-%m-%d) -t h4  -f csv")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
