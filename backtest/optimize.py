"""
Grid-search optimizer: runs on in-sample data (up to IN_SAMPLE_END).
Ranks parameter sets by  expectancy * sqrt(trade_count)  (penalises thin samples).
Requires CSV files in data/. Run data/download.py first.

Usage:  python backtest/optimize.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Optional
from config import SharedParams, TrendFollowingParams, LondonBreakoutParams
from algorithms.trend_following import TrendFollowingStrategy
from algorithms.london_breakout import LondonBreakoutStrategy
from backtest.engine import load_data, run_backtest_fast as run_backtest
from backtest.metrics import compute_metrics, print_metrics

IN_SAMPLE_END = "2024-12-31"
MIN_TRADES = 100  # reject parameter sets below this threshold


def _score(metrics: dict) -> float:
    n = metrics.get("trade_count", 0)
    if n < MIN_TRADES:
        return -float("inf")
    return metrics["expectancy_pips"] * (n ** 0.5)


def optimize_trend(shared: SharedParams) -> Optional[dict]:
    print("\n── Strategy A: Trend-Following optimisation ──────────────────")
    dfs_full = load_data()
    dfs = {k: v[v.index <= IN_SAMPLE_END] for k, v in dfs_full.items()}

    best = None
    best_score = -float("inf")
    count = 0

    for ema_fast in range(5, 13, 2):          # 5, 7, 9, 11
        for ema_slow in range(18, 35, 4):      # 18, 22, 26, 30, 34
            if ema_fast >= ema_slow:
                continue
            for sl_mult in (1.0, 1.5, 2.0, 2.5):
                for tp_mult in (2.0, 2.5, 3.0, 3.5, 4.0):
                    params = TrendFollowingParams(
                        ema_fast=ema_fast, ema_slow=ema_slow,
                        sl_atr_mult=sl_mult, tp_atr_mult=tp_mult,
                    )
                    strategy = TrendFollowingStrategy(params, shared)
                    trades = run_backtest(strategy, shared, dfs)
                    m = compute_metrics(trades)
                    count += 1
                    sc = _score(m)
                    if sc > best_score:
                        best_score = sc
                        best = {"params": params, "metrics": m, "score": sc}

    print(f"Evaluated {count} parameter combinations.")
    if best:
        p = best["params"]
        print(f"Best: ema_fast={p.ema_fast} ema_slow={p.ema_slow} "
              f"sl={p.sl_atr_mult}x tp={p.tp_atr_mult}x  score={best['score']:.2f}")
        print_metrics("Strategy A — In-Sample Best", best["metrics"])
    else:
        print("No parameter set met the minimum trade threshold.")
    return best


def optimize_breakout(shared: SharedParams) -> Optional[dict]:
    print("\n── Strategy B: London Breakout optimisation ──────────────────")
    dfs_full = load_data()
    dfs = {k: v[v.index <= IN_SAMPLE_END] for k, v in dfs_full.items()}

    best = None
    best_score = -float("inf")
    count = 0

    for london_end in range(10, 13):           # 10, 11, 12
        for tp_mult in (1.5, 2.0, 2.5, 3.0):
            for range_max in (1.0, 1.5, 2.0):
                for range_min in (0.2, 0.3, 0.5):
                    if range_min >= range_max:
                        continue
                    params = LondonBreakoutParams(
                        london_end_hour=london_end,
                        tp_range_mult=tp_mult,
                        range_max_atr_mult=range_max,
                        range_min_atr_mult=range_min,
                    )
                    strategy = LondonBreakoutStrategy(params, shared)
                    trades = run_backtest(strategy, shared, dfs)
                    m = compute_metrics(trades)
                    count += 1
                    sc = _score(m)
                    if sc > best_score:
                        best_score = sc
                        best = {"params": params, "metrics": m, "score": sc}

    print(f"Evaluated {count} parameter combinations.")
    if best:
        p = best["params"]
        print(f"Best: london_end={p.london_end_hour}h tp={p.tp_range_mult}x "
              f"range_max={p.range_max_atr_mult}x range_min={p.range_min_atr_mult}x  score={best['score']:.2f}")
        print_metrics("Strategy B — In-Sample Best", best["metrics"])
    else:
        print("No parameter set met the minimum trade threshold.")
    return best


if __name__ == "__main__":
    shared = SharedParams()
    optimize_trend(shared)
    optimize_breakout(shared)
