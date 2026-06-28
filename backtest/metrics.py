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

    # Sharpe annualized by actual trade frequency (not a fixed √252 daily assumption)
    sharpe = 0.0
    if len(profits) > 1:
        std = float(np.std(profits, ddof=1))
        if std > 0:
            times = [t.entry_time for t in trades
                     if t.profit_pts is not None and t.entry_time is not None]
            if len(times) >= 2:
                span_years = max(
                    (max(times) - min(times)).total_seconds() / (365.25 * 86400),
                    1.0 / 52,
                )
                trades_per_year = len(profits) / span_years
            else:
                trades_per_year = 252
            sharpe = float(np.mean(profits)) / std * np.sqrt(trades_per_year)

    return {
        "trade_count":      len(profits),
        "win_rate_%":       round(win_rate * 100, 1),
        "profit_factor":    round(profit_factor, 3),
        "expectancy_pips":  round(expectancy, 3),
        "avg_win_pips":     round(avg_win, 3),
        "avg_loss_pips":    round(avg_loss, 3),
        "max_dd_pips":      round(max_dd, 3),
        "total_profit_pips":round(sum(profits), 3),
        "sharpe":           round(sharpe, 3),
    }


def compute_r_metrics(trades: List[Trade]) -> dict:
    """
    Scale-free R-multiple metrics for cross-symbol ranking.
    1R = distance from entry to initial SL.
    """
    r_multiples = []
    for t in trades:
        if t.profit_pts is None:
            continue
        risk = abs(t.entry_price - t.sl)
        if risk <= 0:
            continue
        r_multiples.append(t.profit_pts / risk)

    if not r_multiples:
        return {}

    wins_r = [r for r in r_multiples if r > 0]
    losses_r = [r for r in r_multiples if r <= 0]

    # Max drawdown in R
    cum_r = np.cumsum(r_multiples)
    peak_r = np.maximum.accumulate(cum_r)
    max_dd_r = float(np.max(peak_r - cum_r)) if len(cum_r) > 0 else 0.0

    return {
        "expectancy_R":  round(float(np.mean(r_multiples)), 3),
        "avg_win_R":     round(float(np.mean(wins_r)), 3) if wins_r else 0.0,
        "avg_loss_R":    round(float(np.mean(losses_r)), 3) if losses_r else 0.0,
        "max_dd_R":      round(max_dd_r, 3),
        "total_R":       round(float(np.sum(r_multiples)), 3),
    }


def print_metrics(header: str, metrics: dict) -> None:
    width = 52
    print(f"\n{'═' * width}")
    print(f"  {header}")
    print(f"{'─' * width}")
    for k, v in metrics.items():
        print(f"  {k:<28} {v}")
    print(f"{'═' * width}")
