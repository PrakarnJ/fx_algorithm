"""
Monte Carlo robustness testing on a backtest's trade list.

Three perturbation families, all operating on realized per-trade profits:
  1. Bootstrap resampling — sample N trades with replacement, 1000 runs:
     confidence intervals on win rate / expectancy / PF, and the max-DD
     distribution (sequence risk).
  2. Trade-skip test — randomly drop 10% of trades per run: does the edge
     survive missing fills?
  3. Slippage stress — subtract extra cost from every trade: how much
     additional slippage (in points) flips expectancy negative?

A strategy is "MC-robust" against the campaign targets when the 5th
percentile of the bootstrap distribution still clears each gate value
(win rate, PF) and the 95th percentile max-DD stays under the DD cap.
"""
import numpy as np


def _max_dd(profits: np.ndarray) -> float:
    cum = np.cumsum(profits)
    peak = np.maximum.accumulate(cum)
    return float(np.max(peak - cum)) if len(cum) else 0.0


def _metrics(profits: np.ndarray) -> tuple:
    wins = profits[profits > 0]
    losses = profits[profits <= 0]
    wr = len(wins) / len(profits) * 100 if len(profits) else 0.0
    gross_loss = abs(losses.sum())
    pf = wins.sum() / gross_loss if gross_loss > 0 else float("inf")
    exp = profits.mean() if len(profits) else 0.0
    return wr, pf, exp, _max_dd(profits)


def run_monte_carlo(
    profits: list,
    n_runs: int = 1000,
    skip_frac: float = 0.10,
    seed: int = 42,
) -> dict:
    """Returns percentile bands for bootstrap, skip-test and slippage stress."""
    p = np.asarray([x for x in profits if x is not None], dtype=float)
    if len(p) < 5:
        return {"valid": False, "reason": f"only {len(p)} trades"}

    rng = np.random.default_rng(seed)
    n = len(p)

    boot = np.empty((n_runs, 4))
    skip = np.empty((n_runs, 4))
    keep = max(1, int(round(n * (1 - skip_frac))))
    for r in range(n_runs):
        boot[r] = _metrics(rng.choice(p, size=n, replace=True))
        skip[r] = _metrics(rng.choice(p, size=keep, replace=False))

    def bands(arr):
        finite = np.where(np.isfinite(arr), arr, np.nan)
        return {
            "p5": round(float(np.nanpercentile(finite, 5)), 3),
            "p50": round(float(np.nanpercentile(finite, 50)), 3),
            "p95": round(float(np.nanpercentile(finite, 95)), 3),
        }

    # Slippage stress: extra per-trade cost (points) that zeroes expectancy.
    # Expectancy is linear in a constant per-trade cost: breakeven = mean(p).
    breakeven_slippage = round(float(p.mean()), 3)

    return {
        "valid": True,
        "n_trades": n,
        "n_runs": n_runs,
        "bootstrap": {
            "win_rate_%": bands(boot[:, 0]),
            "profit_factor": bands(boot[:, 1]),
            "expectancy_pips": bands(boot[:, 2]),
            "max_dd_pips": bands(boot[:, 3]),
        },
        "skip_10pct": {
            "win_rate_%": bands(skip[:, 0]),
            "profit_factor": bands(skip[:, 1]),
            "expectancy_pips": bands(skip[:, 2]),
            "max_dd_pips": bands(skip[:, 3]),
        },
        "breakeven_extra_slippage_pips": breakeven_slippage,
    }


def mc_passes_targets(mc: dict, wr_min: float, pf_min: float, dd_max: float) -> dict:
    """Conservative MC gate: 5th-pct WR/PF above minimums, 95th-pct DD under cap."""
    if not mc.get("valid"):
        return {"passed": False, "reason": mc.get("reason", "invalid")}
    b = mc["bootstrap"]
    checks = {
        "wr_p5": b["win_rate_%"]["p5"] >= wr_min,
        "pf_p5": b["profit_factor"]["p5"] >= pf_min,
        "dd_p95": b["max_dd_pips"]["p95"] < dd_max,
        "exp_p5_positive": b["expectancy_pips"]["p5"] > 0,
    }
    return {"passed": all(checks.values()), "checks": checks}
