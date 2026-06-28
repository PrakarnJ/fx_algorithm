"""
Head-to-head comparison of Strategy A vs Strategy B.

Steps:
  1. In-sample grid search to find the best parameters for each strategy.
  2. Walk-forward OOS evaluation on identical unseen data.
  3. Decision: recommend whichever strategy has higher OOS expectancy
     and passes the acceptance gate.  If neither passes, report honestly.

Run from the forex_algorithm/ directory:
    python backtest/compare.py

After running, update ACTIVE_STRATEGY in config.py.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import SharedParams
from backtest.optimize import optimize_trend, optimize_breakout
from backtest.walk_forward import run_walk_forward
from algorithms.trend_following import TrendFollowingStrategy
from algorithms.london_breakout import LondonBreakoutStrategy


def compare() -> None:
    shared = SharedParams()

    print("╔══════════════════════════════════════════════════════╗")
    print("║  PHASE 1 — In-sample optimisation (2022–2024)        ║")
    print("╚══════════════════════════════════════════════════════╝")
    best_a = optimize_trend(shared)
    best_b = optimize_breakout(shared)

    print("\n╔══════════════════════════════════════════════════════╗")
    print("║  PHASE 2 — Walk-forward OOS validation (2025–now)    ║")
    print("╚══════════════════════════════════════════════════════╝")

    results = {}

    if best_a:
        strat_a = TrendFollowingStrategy(best_a["params"], shared)
        metrics_a, passed_a = run_walk_forward(strat_a, "Strategy A (Trend-Following)", shared)
        results["A"] = {"metrics": metrics_a, "passed": passed_a, "label": "trend"}

    if best_b:
        strat_b = LondonBreakoutStrategy(best_b["params"], shared)
        metrics_b, passed_b = run_walk_forward(strat_b, "Strategy B (London Breakout)", shared)
        results["B"] = {"metrics": metrics_b, "passed": passed_b, "label": "breakout"}

    print("\n╔══════════════════════════════════════════════════════╗")
    print("║  DECISION                                            ║")
    print("╚══════════════════════════════════════════════════════╝")

    viable = {k: v for k, v in results.items() if v["passed"]}

    if not viable:
        print("\n  ⚠  Neither strategy passed OOS acceptance criteria.")
        print("  Do NOT deploy with real money.")
        print("  Consider: expanding data range, relaxing parameters, or redesigning.")
        return

    winner_key = max(viable, key=lambda k: viable[k]["metrics"].get("expectancy_pips", 0))
    winner = viable[winner_key]
    exp = winner["metrics"]["expectancy_pips"]
    pf = winner["metrics"]["profit_factor"]

    print(f"\n  Recommended: Strategy {winner_key}  ({winner['label']})")
    print(f"  OOS expectancy = {exp:.3f} pts/trade   profit factor = {pf:.3f}")
    print(f"\n  → Set  ACTIVE_STRATEGY = '{winner['label']}'  in config.py")

    if len(viable) == 2:
        loser_key = [k for k in viable if k != winner_key][0]
        print(f"  (Both passed; Strategy {loser_key} also viable — consider running both on demo)")


if __name__ == "__main__":
    compare()
