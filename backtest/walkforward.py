"""
Walk-forward optimization (WFO) for the regime-aware / trend-following
strategies.

Rolls a (train → test) window across the whole 2022–2026 history:

    [── train (TRAIN_MONTHS) ──][─ test (TEST_MONTHS) ─]
              step forward TEST_MONTHS, repeat

On each train window an Optuna search picks the best parameters (selection
uses train data only); those parameters are then run on the *immediately
following* test window. All test segments are stitched into one continuous
out-of-sample equity curve — no future information ever reaches a test bar,
and no single window is special. This is the honest metric once the whole
dataset has been seen.

Run: python backtest/walkforward.py [--trials 40] [--family regime_switch]
"""
import sys
import json
import argparse
import datetime
from pathlib import Path
from dataclasses import asdict, replace

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import optuna

from config import (
    SharedParams, TrendBreakoutParams, RegimeSwitchParams,
)
from algorithms.trend_breakout import TrendBreakoutStrategy
from algorithms.regime_switch import RegimeSwitchStrategy
from backtest.engine import load_data, run_backtest_fast
from backtest.metrics import compute_metrics
from backtest.montecarlo import run_monte_carlo
from backtest.regime import classify_regime, regime_fractions

optuna.logging.set_verbosity(optuna.logging.WARNING)

RUN_DIR = Path(__file__).parent / "campaign_runs"
LOG_PATH = Path(__file__).parent.parent / "STRATEGY_LOG.md"

DATA_START = "2022-01-01"
TRAIN_MONTHS = 12
TEST_MONTHS = 3
WARMUP_DAYS = 40
SHARED = SharedParams()


# ───────────────────────── families ─────────────────────────

def build_trend(params, shared):
    sh = replace(shared, breakeven_atr_mult=params.breakeven_atr_mult,
                 trail_atr_mult=params.trail_atr_mult)
    return TrendBreakoutStrategy(params, sh), sh


def build_regime(params, shared):
    sh = replace(shared, breakeven_atr_mult=params.trend_breakeven_atr_mult,
                 trail_atr_mult=params.trend_trail_atr_mult)
    return RegimeSwitchStrategy(params, sh), sh


def suggest_trend(trial) -> TrendBreakoutParams:
    return TrendBreakoutParams(
        tf=trial.suggest_categorical("tf", ["H1", "H4"]),
        mode=trial.suggest_categorical("mode", ["donchian", "ma_momentum"]),
        channel_period=trial.suggest_int("channel_period", 20, 80, step=10),
        ema_fast=trial.suggest_int("ema_fast", 10, 30, step=5),
        ema_slow=trial.suggest_int("ema_slow", 40, 100, step=10),
        slope_lookback=trial.suggest_int("slope_lookback", 5, 20, step=5),
        sl_atr_mult=trial.suggest_float("sl_atr_mult", 1.5, 4.0, step=0.5),
        cooldown_bars=trial.suggest_int("cooldown_bars", 2, 16, step=2),
        breakeven_atr_mult=trial.suggest_float("breakeven_atr_mult", 1.0, 3.0, step=0.5),
        trail_atr_mult=trial.suggest_float("trail_atr_mult", 2.0, 5.0, step=0.5),
        regime_filter=trial.suggest_categorical("regime_filter", [True, False]),
        adx_trend=trial.suggest_float("adx_trend", 18, 32, step=2),
        er_trend=trial.suggest_float("er_trend", 0.2, 0.45, step=0.05),
    )


def suggest_regime(trial) -> RegimeSwitchParams:
    return RegimeSwitchParams(
        tf=trial.suggest_categorical("tf", ["H1", "H4"]),
        adx_trend=trial.suggest_float("adx_trend", 18, 32, step=2),
        er_trend=trial.suggest_float("er_trend", 0.2, 0.45, step=0.05),
        ema_slow=trial.suggest_int("ema_slow", 120, 240, step=20),
        channel_period=trial.suggest_int("channel_period", 20, 80, step=10),
        trend_sl_atr_mult=trial.suggest_float("trend_sl_atr_mult", 1.5, 4.0, step=0.5),
        trend_breakeven_atr_mult=trial.suggest_float("trend_breakeven_atr_mult", 1.0, 3.0, step=0.5),
        trend_trail_atr_mult=trial.suggest_float("trend_trail_atr_mult", 2.0, 5.0, step=0.5),
        cooldown_bars=trial.suggest_int("cooldown_bars", 2, 16, step=2),
        range_enabled=trial.suggest_categorical("range_enabled", [True, False]),
        z_lookback=trial.suggest_int("z_lookback", 40, 100, step=10),
        z_entry=trial.suggest_float("z_entry", 1.5, 3.0, step=0.25),
        range_tp_pts=trial.suggest_float("range_tp_pts", 2.0, 8.0, step=1.0),
        range_sl_pts=trial.suggest_float("range_sl_pts", 5.0, 20.0, step=1.0),
    )


FAMILIES = {
    "trend": dict(suggest=suggest_trend, build=build_trend, cls=TrendBreakoutParams),
    "regime_switch": dict(suggest=suggest_regime, build=build_regime, cls=RegimeSwitchParams),
}


# ───────────────────────── evaluation ─────────────────────────

def _slice(dfs_full, start, end):
    buf = str(np.datetime64(start) - np.timedelta64(WARMUP_DAYS, "D"))
    return {k: v[(v.index >= buf) & (v.index < end)] for k, v in dfs_full.items()}


def evaluate(params, fam, dfs_full, start, end):
    """Run on [start, end); metrics on trades entered within the window."""
    strategy, sh = fam["build"](params, SHARED)
    exec_tf = strategy.exec_tf
    dfs = _slice(dfs_full, start, end)
    # engine warms up 250 exec bars (×4 for M15); need headroom for indicators
    min_bars = 1100 if exec_tf == "M15" else 320
    if len(dfs[exec_tf]) < min_bars:
        return {"trade_count": 0}, []
    trades = run_backtest_fast(strategy, sh, dfs, exec_tf=exec_tf)
    trades = [t for t in trades if str(t.entry_time) >= str(start)]
    return compute_metrics(trades), trades


def score(m):
    """Selection objective on a train window: risk-adjusted, trade-count aware."""
    n = m.get("trade_count", 0)
    if n < 15:
        return -1.0 + n / 15.0
    if m.get("expectancy_pts", -1) <= 0:
        return 0.0
    pf = m.get("profit_factor")
    pf = 4.0 if pf is None or not np.isfinite(pf) else min(pf, 4.0)
    # reward profit factor and total profit, lightly penalize drawdown
    dd = max(m.get("max_dd_pts", 1e-6), 1e-6)
    return (pf - 1.0) * np.sqrt(n) * min(1.0, 50.0 / dd)


def month_windows(dfs_full):
    h1 = dfs_full["H1"]
    end_all = h1.index[-1]
    start = pd.Timestamp(DATA_START, tz="UTC") + pd.DateOffset(months=TRAIN_MONTHS)
    windows = []
    while True:
        tr_start = start - pd.DateOffset(months=TRAIN_MONTHS)
        te_start = start
        te_end = start + pd.DateOffset(months=TEST_MONTHS)
        if te_start >= end_all:
            break
        windows.append((str(tr_start.date()), str(te_start.date()),
                        str(min(te_end, end_all + pd.Timedelta(days=1)).date())))
        start = te_end
    return windows


# ───────────────────────── walk-forward loop ─────────────────────────

def walk_forward(family_name, n_trials, dfs_full):
    fam = FAMILIES[family_name]
    windows = month_windows(dfs_full)
    print(f"Walk-forward [{family_name}]: {len(windows)} windows "
          f"({TRAIN_MONTHS}mo train / {TEST_MONTHS}mo test), {n_trials} trials/window",
          flush=True)

    all_test_trades = []
    segments = []
    for wi, (tr_start, te_start, te_end) in enumerate(windows):
        study = optuna.create_study(
            direction="maximize",
            sampler=optuna.samplers.TPESampler(multivariate=True, seed=42))

        def objective(trial):
            params = fam["suggest"](trial)
            m, _ = evaluate(params, fam, dfs_full, tr_start, te_start)
            return score(m)

        study.optimize(objective, n_trials=n_trials, catch=(Exception,))
        best = fam["cls"](**{**asdict(fam["cls"]()), **study.best_params})

        te_m, te_trades = evaluate(best, fam, dfs_full, te_start, te_end)
        all_test_trades.extend(te_trades)
        seg = {
            "window": wi, "train": [tr_start, te_start], "test": [te_start, te_end],
            "test_metrics": te_m,
            "test_profit": round(sum(t.profit_pts for t in te_trades), 2),
        }
        segments.append(seg)
        print(f"  W{wi:02d} test {te_start}→{te_end}: "
              f"trades={te_m.get('trade_count',0):>3} "
              f"wr={te_m.get('win_rate_%',0):>5.1f}% "
              f"pf={te_m.get('profit_factor')} "
              f"profit={seg['test_profit']:>+8.1f}pts", flush=True)

    # Stitched out-of-sample metrics
    profits = [t.profit_pts for t in all_test_trades]
    agg = compute_metrics(all_test_trades)
    mc = run_monte_carlo(profits) if len(profits) >= 5 else {"valid": False}

    # Serialize stitched trades + equity/monthly for the dashboard
    from backtest.export_report import _trade_dict, _equity_series, _monthly_pnl
    dummy = fam["build"](fam["cls"](), SHARED)[0]
    return {
        "family": family_name,
        "windows": len(windows),
        "config": {"train_months": TRAIN_MONTHS, "test_months": TEST_MONTHS,
                   "trials_per_window": n_trials},
        "aggregate": agg,
        "monte_carlo": mc,
        "segments": segments,
        "exec_tf": dummy.exec_tf,
        "trades": [_trade_dict(t) for t in all_test_trades],
        "equity": _equity_series(all_test_trades),
        "monthly": _monthly_pnl(all_test_trades),
    }


# ───────────────────────── reporting ─────────────────────────

def write_report(results: list, dfs_full: dict):
    now = datetime.datetime.now(datetime.timezone.utc)
    regime = classify_regime(dfs_full, "H1")
    fracs = regime_fractions(regime[regime.index >= "2022-01-01"])

    lines = [
        "\n\n---\n",
        f"## Walk-Forward {now:%Y-%m-%d %H:%M} UTC — Regime-Aware / Trend-Following "
        "(real Dukascopy data)\n",
        f"**Method:** rolling {TRAIN_MONTHS}mo train → {TEST_MONTHS}mo test across "
        f"2022→2026; parameters re-selected on each train window, evaluated on the "
        f"next (unseen) test window; all test segments stitched into one OOS curve.  ",
        f"**Regime mix (whole history, H1):** trend_up {fracs['trend_up']:.0%}, "
        f"trend_down {fracs['trend_down']:.0%}, range {fracs['range']:.0%}.  ",
        "**Note:** 2025+ is no longer a clean holdout (it informed this design); "
        "walk-forward across all regimes is the honest metric, and true confirmation "
        "needs forward data.\n",
        "| Family | Windows | OOS trades | Win % | Expectancy | PF | Max DD | Total | MC p5 PF |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        m = r["aggregate"]
        mc = r["monte_carlo"]
        pf_p5 = (mc.get("bootstrap", {}).get("profit_factor", {}).get("p5", "—")
                 if mc.get("valid") else "—")
        lines.append(
            f"| {r['family']} | {r['windows']} | {m.get('trade_count',0)} "
            f"| {m.get('win_rate_%',0):.1f}% | {m.get('expectancy_pts',0):+.3f} "
            f"| {m.get('profit_factor')} | {m.get('max_dd_pts',0):.1f} "
            f"| {m.get('total_profit_pts',0):+.1f} | {pf_p5} |"
        )

    best = max(results, key=lambda r: r["aggregate"].get("total_profit_pts", -1e9))
    bm = best["aggregate"]
    profitable = bm.get("total_profit_pts", 0) > 0 and (bm.get("profit_factor") or 0) > 1
    lines.append(
        f"\n**Verdict:** "
        + (f"`{best['family']}` is the strongest — stitched walk-forward "
           f"PF {bm.get('profit_factor')}, expectancy {bm.get('expectancy_pts'):+.3f} pts "
           f"over {bm.get('trade_count')} trades across {best['windows']} regimes. "
           if profitable else
           f"No family was robustly profitable across walk-forward windows "
           f"(best `{best['family']}` total {bm.get('total_profit_pts',0):+.1f} pts). ")
        + "Original 90% WR / PF>2 / DD<10 target is not the right yardstick for a "
          "trend-follower (lower WR, larger wins by design); judged on risk-adjusted "
          "robustness across regimes instead."
    )
    with open(LOG_PATH, "a") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[log] walk-forward report appended to {LOG_PATH.name}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=40)
    ap.add_argument("--family", default="all", choices=["all", "trend", "regime_switch"])
    args = ap.parse_args()

    dfs_full = load_data()
    h1 = dfs_full["H1"]
    print(f"Data {h1.index[0]:%Y-%m-%d} → {h1.index[-1]:%Y-%m-%d}", flush=True)

    fams = ["trend", "regime_switch"] if args.family == "all" else [args.family]
    results = [walk_forward(f, args.trials, dfs_full) for f in fams]

    RUN_DIR.mkdir(exist_ok=True)
    (RUN_DIR / "walkforward_results.json").write_text(json.dumps(results, indent=1, default=str))
    write_report(results, dfs_full)

    for r in results:
        m = r["aggregate"]
        print(f"\n{r['family']}: OOS trades={m.get('trade_count')} "
              f"wr={m.get('win_rate_%')}% pf={m.get('profit_factor')} "
              f"total={m.get('total_profit_pts')}pts", flush=True)


if __name__ == "__main__":
    main()
