"""
Export backtest results as JSON for the web dashboard in report/.

Re-runs the deterministic backtests for the four reproducible configurations
(synthetic data is seeded, so results match STRATEGY_LOG.md exactly) and
writes report/data.json with metrics, trades, equity curves and the master
variant table.

Run: python backtest/export_report.py
Then: python -m http.server 8765 -d report
"""
import sys
import json
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dataclasses import asdict
import numpy as np
import pandas as pd

from config import (
    SYMBOL, SharedParams, TrendFollowingParams, LondonBreakoutParams,
    BREAKOUT_PARAMS,
)
from algorithms.trend_following import TrendFollowingStrategy
from algorithms.london_breakout import LondonBreakoutStrategy
from backtest.engine import load_data, run_backtest_fast
from backtest.metrics import compute_metrics
from backtest.walk_forward import OOS_START, ACCEPTANCE

REPORT_DIR = Path(__file__).parent.parent / "report"

VARIANTS = [
    dict(
        key="B-deployed",
        label="B — London Breakout (deployed)",
        strategy="London Breakout",
        desc="Live config.py BREAKOUT_PARAMS: london_end=11h + partial TP @1R, "
             "trend filter, ADX>20, 8h time-stop",
        cls=LondonBreakoutStrategy,
        params=BREAKOUT_PARAMS,
    ),
    dict(
        key="B-v4",
        label="B-v4 — London Breakout (logged best)",
        strategy="London Breakout",
        desc="STRATEGY_LOG.md final best: london_end=12h + the same 4 boosters",
        cls=LondonBreakoutStrategy,
        params=LondonBreakoutParams(
            london_end_hour=12, tp_range_mult=3.0,
            range_max_atr_mult=2.0, range_min_atr_mult=0.2,
            partial_tp_enabled=True, partial_tp_r=1.0,
            trend_filter=True, adx_min=20.0, time_stop_hours=8,
        ),
    ),
    dict(
        key="B-baseline",
        label="B — London Breakout (baseline)",
        strategy="London Breakout",
        desc="Asian-range breakout, no boosters: london_end=12h, tp=3.0×range, "
             "range 0.2–2.0×ATR",
        cls=LondonBreakoutStrategy,
        params=LondonBreakoutParams(
            london_end_hour=12, tp_range_mult=3.0,
            range_max_atr_mult=2.0, range_min_atr_mult=0.2,
        ),
    ),
    dict(
        key="A-best",
        label="A — Trend-Following (best IS params)",
        strategy="Trend-Following",
        desc="EMA 9/18 crossover on H1, H4 EMA(50) bias, RSI filter, "
             "SL=2.5×ATR TP=2.0×ATR — failed OOS validation",
        cls=TrendFollowingStrategy,
        params=TrendFollowingParams(
            ema_fast=9, ema_slow=18, sl_atr_mult=2.5, tp_atr_mult=2.0,
        ),
    ),
]

# All variants ever tested, as recorded in STRATEGY_LOG.md (OOS metrics).
MASTER_TABLE = [
    dict(name="A-baseline",        desc="EMA 9/21 crossover + RSI(14) + H4 EMA(50) trend",
         oos_trades=66, oos_wr=66.7, oos_exp=-0.023, oos_pf=1.000, oos_dd=158.8, verdict="FAIL"),
    dict(name="B-baseline",        desc="London breakout (london_end=12h, tp=3.0×, rmax=2.0×, rmin=0.2×)",
         oos_trades=88, oos_wr=54.5, oos_exp=7.246,  oos_pf=1.994, oos_dd=119.4, verdict="PASS"),
    dict(name="B-v1-partial-tp",   desc="+ Partial TP at 1R (close 50%, move SL to BE)",
         oos_trades=87, oos_wr=55.2, oos_exp=4.243,  oos_pf=1.594, oos_dd=126.0, verdict="KEPT"),
    dict(name="B-v2-trend-filt",   desc="+ H4/H1 EMA(50) trend-alignment filter",
         oos_trades=43, oos_wr=55.8, oos_exp=4.673,  oos_pf=1.647, oos_dd=83.1,  verdict="KEPT"),
    dict(name="B-v3-adx-filt",     desc="+ ADX(14) > 20 filter on H1",
         oos_trades=32, oos_wr=56.2, oos_exp=5.247,  oos_pf=1.719, oos_dd=53.3,  verdict="KEPT"),
    dict(name="B-v4-time-stop",    desc="+ Time-stop after 8 H1 bars",
         oos_trades=32, oos_wr=62.5, oos_exp=6.309,  oos_pf=2.022, oos_dd=35.7,  verdict="KEPT"),
    dict(name="B-v5-early-partial", desc="+ Earlier partial TP at 0.5R",
         oos_trades=14, oos_wr=57.1, oos_exp=5.413,  oos_pf=1.842, oos_dd=30.3,  verdict="REJECTED"),
    dict(name="B-v6-closer-tp",    desc="+ Re-optimized TP toward 1.0–2.0× range",
         oos_trades=14, oos_wr=57.1, oos_exp=7.423,  oos_pf=2.155, oos_dd=30.3,  verdict="REJECTED"),
    dict(name="B-v7-wr-objective", desc="+ Re-optimized with win-rate objective",
         oos_trades=13, oos_wr=53.8, oos_exp=2.026,  oos_pf=1.293, oos_dd=41.3,  verdict="REJECTED"),
    dict(name="B-v8-tight-trail",  desc="+ Tighter trail after partial (0.75×ATR)",
         oos_trades=14, oos_wr=57.1, oos_exp=7.423,  oos_pf=2.155, oos_dd=30.3,  verdict="REJECTED"),
    dict(name="B-v9-scalp-mode",   desc="+ Scalp mode: close 100% at partial TP",
         oos_trades=14, oos_wr=57.1, oos_exp=1.496,  oos_pf=1.233, oos_dd=33.3,  verdict="REJECTED"),
    dict(name="FINAL BEST (B-v4)", desc="All kept enhancements combined",
         oos_trades=32, oos_wr=62.5, oos_exp=6.309,  oos_pf=2.022, oos_dd=35.7,  verdict="BEST"),
]


def _jsonable_metrics(m: dict) -> dict:
    out = {}
    for k, v in m.items():
        if isinstance(v, (np.floating, np.integer)):
            v = float(v)
        if isinstance(v, float) and np.isinf(v):
            v = None  # rendered as ∞ in the UI
        out[k] = v
    return out


def _trade_dict(t) -> dict:
    return {
        "entry_time": t.entry_time.isoformat(),
        "exit_time": t.exit_time.isoformat() if t.exit_time is not None else None,
        "direction": t.direction,
        "entry": round(t.entry_price, 2),
        "exit": round(t.exit_price, 2) if t.exit_price is not None else None,
        "sl": round(t.sl, 2),
        "tp": round(t.tp, 2),
        "profit_pts": round(t.profit_pts, 3) if t.profit_pts is not None else None,
        "partial": bool(t.partial_done),
    }


def _equity_series(trades) -> list:
    points, cum, peak = [], 0.0, 0.0
    for t in trades:
        cum += t.profit_pts
        peak = max(peak, cum)
        points.append({
            "t": t.exit_time.isoformat(),
            "cum": round(cum, 3),
            "dd": round(peak - cum, 3),
        })
    return points


def _monthly_pnl(trades) -> list:
    if not trades:
        return []
    s = pd.Series(
        [t.profit_pts for t in trades],
        index=pd.DatetimeIndex([t.exit_time for t in trades]).tz_localize(None),
    )
    grouped = s.groupby(s.index.to_period("M")).sum()
    return [{"month": str(p), "pnl": round(float(v), 3)} for p, v in grouped.items()]


def _run_window(variant: dict, shared: SharedParams, dfs: dict) -> dict:
    strategy = variant["cls"](variant["params"], shared)
    trades = run_backtest_fast(strategy, shared, dfs)
    return {
        "metrics": _jsonable_metrics(compute_metrics(trades)),
        "trades": [_trade_dict(t) for t in trades],
        "equity": _equity_series(trades),
        "monthly": _monthly_pnl(trades),
    }


WF_RESULTS = Path(__file__).parent / "campaign_runs" / "walkforward_results.json"

WF_META = {
    "regime_switch": dict(
        label="★ Regime-Aware Switch (walk-forward)",
        strategy="Regime Switch",
        desc="Trend-follow in trends, mean-revert/stand-aside in ranges. Walk-forward "
             "OOS: params re-selected on each 12mo train window, tested on the next 3mo. "
             "NOTE: ~69% of profit is from the 2026 Q1 parabolic spike — real edge but "
             "tail-driven (trend-following positive skew).",
        verdict="WALK-FWD",
    ),
    "trend": dict(
        label="Trend-Following (walk-forward)",
        strategy="Trend-Following",
        desc="Donchian / MA-momentum riding with the trend, ATR trailing stop. "
             "Walk-forward OOS across all 2022–2026 regimes.",
        verdict="WALK-FWD",
    ),
}


def load_walkforward() -> tuple:
    """Returns (wf_variants, wf_master_rows) from the walk-forward results JSON."""
    if not WF_RESULTS.exists():
        return [], []
    results = json.loads(WF_RESULTS.read_text())
    variants, rows = [], []
    for r in results:
        fam = r["family"]
        meta = WF_META.get(fam, dict(label=fam, strategy=fam, desc="", verdict="WALK-FWD"))
        m = _jsonable_metrics(r["aggregate"])
        variants.append({
            "key": f"{fam}-wf",
            "label": meta["label"],
            "strategy": meta["strategy"],
            "desc": meta["desc"],
            "params": {"method": f"walk-forward {r['config']['train_months']}mo→"
                       f"{r['config']['test_months']}mo", "windows": r["windows"]},
            "windows": {"walkforward": {
                "metrics": m, "trades": r.get("trades", []),
                "equity": r.get("equity", []), "monthly": r.get("monthly", []),
            }},
            "walkforward": True,
            "monte_carlo": r.get("monte_carlo"),
        })
        rows.append(dict(
            name=meta["label"].replace("★ ", ""), desc=meta["desc"][:80],
            oos_trades=m.get("trade_count", 0), oos_wr=m.get("win_rate_%", 0),
            oos_exp=m.get("expectancy_pts", 0), oos_pf=m.get("profit_factor") or 0,
            oos_dd=m.get("max_dd_pts", 0), verdict=meta["verdict"],
        ))
    # regime_switch first (it's the headline)
    variants.sort(key=lambda v: 0 if "regime" in v["key"] else 1)
    rows.sort(key=lambda r: 0 if "Regime" in r["name"] else 1)
    return variants, rows


def main() -> None:
    shared = SharedParams()
    dfs_full = load_data()
    dfs_oos = {k: v[v.index >= OOS_START] for k, v in dfs_full.items()}
    h1 = dfs_full["H1"]

    variants_out = []
    for v in VARIANTS:
        print(f"Running {v['key']} ...")
        windows = {
            "oos": _run_window(v, shared, dfs_oos),
            "full": _run_window(v, shared, dfs_full),
        }
        for wname, w in windows.items():
            m = w["metrics"]
            print(f"  {wname:<4}  trades={m.get('trade_count', 0):>3}  "
                  f"wr={m.get('win_rate_%', 0)}%  pf={m.get('profit_factor')}  "
                  f"exp={m.get('expectancy_pts')}")
        variants_out.append({
            "key": v["key"],
            "label": v["label"],
            "strategy": v["strategy"],
            "desc": v["desc"],
            "params": asdict(v["params"]),
            "windows": windows,
        })

    # Fold in walk-forward variants (regime_switch, trend) — the headline result
    wf_variants, wf_rows = load_walkforward()
    if wf_variants:
        variants_out = wf_variants + variants_out   # regime_switch first
        print(f"Folded in {len(wf_variants)} walk-forward variant(s)")

    data = {
        "meta": {
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "symbol": SYMBOL,
            "data_source": "Real XAUUSD (Dukascopy) 2022–2026. Walk-forward variants are "
                           "true out-of-sample; single-window variants run on the same real data.",
            "data_start": h1.index[0].isoformat(),
            "data_end": h1.index[-1].isoformat(),
            "oos_start": OOS_START,
            "gate": ACCEPTANCE,
        },
        "variants": variants_out,
        "master_table": wf_rows + MASTER_TABLE,
    }

    REPORT_DIR.mkdir(exist_ok=True)
    out_path = REPORT_DIR / "data.json"
    out_path.write_text(json.dumps(data, separators=(",", ":")))
    print(f"\nWrote {out_path}  ({out_path.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
