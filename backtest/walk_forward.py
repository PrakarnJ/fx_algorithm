"""
Out-of-sample walk-forward validation.
Takes the best parameters found by optimize.py and evaluates them
on data the optimiser never saw (OOS_START → present).

Usage (standalone):  python backtest/walk_forward.py
Normally called from compare.py.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Tuple
from config import SharedParams
from backtest.engine import load_data, run_backtest_fast as run_backtest
from backtest.metrics import compute_metrics, print_metrics

OOS_START = "2025-01-01"

ACCEPTANCE = {
    "profit_factor_min": 1.3,
    "expectancy_min":    0.0,
    "min_trades":        30,
}


def run_walk_forward(
    strategy,
    name: str,
    shared: SharedParams,
) -> Tuple[dict, bool]:
    dfs_full = load_data()
    dfs_oos = {k: v[v.index >= OOS_START] for k, v in dfs_full.items()}

    trades = run_backtest(strategy, shared, dfs_oos)
    metrics = compute_metrics(trades)
    print_metrics(f"Walk-Forward OOS — {name}", metrics)

    passed = (
        metrics.get("trade_count", 0) >= ACCEPTANCE["min_trades"]
        and metrics.get("profit_factor", 0) >= ACCEPTANCE["profit_factor_min"]
        and metrics.get("expectancy_pts", -1) > ACCEPTANCE["expectancy_min"]
    )
    label = "✓ PASS" if passed else "✗ FAIL"
    print(f"  Acceptance gate: {label}")
    return metrics, passed
