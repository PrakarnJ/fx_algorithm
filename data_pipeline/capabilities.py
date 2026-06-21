"""Check whether enough data exists to run a given algo on a given symbol."""
from pathlib import Path
from typing import Tuple

import pandas as pd

from algorithms.registry import TF_TO_FILE
from config import STOCKS_DIR

MIN_BARS: dict[str, int] = {
    "M1": 5000,
    "M5": 2000,
    "M15": 1000,
    "M30": 800,
    "H1": 500,
    "H4": 200,
    "D1": 100,
    "W1": 50,
    "MN": 24,
}


def check_capability(
    symbol: str,
    required_tfs: list[str],
    stocks_dir: Path = STOCKS_DIR,
) -> Tuple[bool, str]:
    """
    Return (can_run, reason).
    Checks each required TF CSV exists and has >= MIN_BARS rows.
    """
    sym_dir = stocks_dir / symbol
    for tf in required_tfs:
        fname = TF_TO_FILE.get(tf)
        if not fname:
            return False, f"Unknown TF key '{tf}'"
        path = sym_dir / fname
        if not path.exists():
            return False, f"Missing {tf} data for {symbol} (expected {path})"
        try:
            n = sum(1 for _ in open(path)) - 1  # fast line count (subtract header)
        except Exception as e:
            return False, f"Cannot read {path}: {e}"
        min_req = MIN_BARS.get(tf, 50)
        if n < min_req:
            return False, f"{symbol} {tf}: only {n} bars (need ≥ {min_req})"
    return True, ""


def available_tfs(symbol: str, stocks_dir: Path = STOCKS_DIR) -> list[str]:
    """Return list of internal TF keys for which CSV files exist."""
    sym_dir = stocks_dir / symbol
    if not sym_dir.exists():
        return []
    found = []
    for tf, fname in TF_TO_FILE.items():
        if (sym_dir / fname).exists():
            found.append(tf)
    return found
