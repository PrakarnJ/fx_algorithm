import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import List
import numpy as np
from backtest.engine import Trade


def compute_metrics(trades: List[Trade]) -> dict:
    profits = [t.profit_pts for t in trades if t.profit_pts is not None]
    if not profits:
        return {"trade_count": 0}

    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p <= 0]

    win_rate = len(wins) / len(profits)
    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = float(abs(np.mean(losses))) if losses else 0.0

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    expectancy = win_rate * avg_win - (1 - win_rate) * avg_loss

    # Max drawdown on cumulative profit curve
    cum = np.cumsum(profits)
    peak = np.maximum.accumulate(cum)
    max_dd = float(np.max(peak - cum)) if len(cum) > 0 else 0.0

    # Per-trade Sharpe approximation
    sharpe = 0.0
    if len(profits) > 1:
        std = float(np.std(profits, ddof=1))
        if std > 0:
            sharpe = float(np.mean(profits)) / std * np.sqrt(252)

    return {
        "trade_count":     len(profits),
        "win_rate_%":      round(win_rate * 100, 1),
        "profit_factor":   round(profit_factor, 3),
        "expectancy_pts":  round(expectancy, 3),
        "avg_win_pts":     round(avg_win, 3),
        "avg_loss_pts":    round(avg_loss, 3),
        "max_dd_pts":      round(max_dd, 3),
        "total_profit_pts":round(sum(profits), 3),
        "sharpe":          round(sharpe, 3),
    }


def print_metrics(header: str, metrics: dict) -> None:
    width = 52
    print(f"\n{'═' * width}")
    print(f"  {header}")
    print(f"{'─' * width}")
    for k, v in metrics.items():
        print(f"  {k:<28} {v}")
    print(f"{'═' * width}")
