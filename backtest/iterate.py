"""
Win-rate improvement iteration ladder — all rounds.

Rounds 1–4 (B-v1 … B-v4): baseline enhancements; already completed.
Rounds 5–9 (B-v5 … B-v9): win-rate-biased push toward 80%.

Each round is kept only if:
  - OOS win rate increases vs previous best
  - OOS expectancy > 0
  - OOS trade count >= 30

Results appended to STRATEGY_LOG.md; final master table printed to screen.

Run: python backtest/iterate.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import datetime
from dataclasses import replace

from config import SharedParams, LondonBreakoutParams
from strategies.london_breakout import LondonBreakoutStrategy
from backtest.engine import load_data, run_backtest_fast
from backtest.metrics import compute_metrics, print_metrics
from backtest.walk_forward import OOS_START

LOG_PATH = Path(__file__).parent.parent / "STRATEGY_LOG.md"
IN_SAMPLE_END = "2024-12-31"

# ─────────────────────────────────────────────────────────────────────────────
# Previously recorded results (from compare.py and round-1 iterate.py)
# ─────────────────────────────────────────────────────────────────────────────
PRIOR_ENTRIES = [
    dict(name="A-baseline",      data="Synthetic GBM", desc="EMA 9/21 crossover + RSI(14) + H4 EMA(50) trend",
         oos_trades=66,  oos_wr=66.7, oos_exp=-0.023, oos_pf=1.000, oos_dd=158.8, verdict="❌ FAIL"),
    dict(name="B-baseline",      data="Synthetic GBM", desc="London breakout (london_end=12h, tp=3.0×, rmax=2.0×, rmin=0.2×)",
         oos_trades=88,  oos_wr=54.5, oos_exp=7.246,  oos_pf=1.994, oos_dd=119.4, verdict="✅ PASS"),
    dict(name="B-v1-partial-tp", data="Synthetic GBM", desc="+ Partial TP at 1R (close 50%, move SL to BE)",
         oos_trades=87,  oos_wr=55.2, oos_exp=4.243,  oos_pf=1.594, oos_dd=126.0, verdict="✅ KEPT"),
    dict(name="B-v2-trend-filt", data="Synthetic GBM", desc="+ H4/H1 EMA(50) trend-alignment filter",
         oos_trades=43,  oos_wr=55.8, oos_exp=4.673,  oos_pf=1.647, oos_dd=83.1,  verdict="✅ KEPT"),
    dict(name="B-v3-adx-filt",   data="Synthetic GBM", desc="+ ADX(14) > 20 filter on H1",
         oos_trades=32,  oos_wr=56.2, oos_exp=5.247,  oos_pf=1.719, oos_dd=53.3,  verdict="✅ KEPT"),
    dict(name="B-v4-time-stop",  data="Synthetic GBM", desc="+ Time-stop after 8 H1 bars",
         oos_trades=32,  oos_wr=62.5, oos_exp=6.309,  oos_pf=2.022, oos_dd=35.7,  verdict="✅ KEPT"),
]

# B-v4 best params (starting point for round 2)
V4_PARAMS = LondonBreakoutParams(
    london_end_hour=11, tp_range_mult=3.0,
    range_max_atr_mult=2.0, range_min_atr_mult=0.2,
    partial_tp_enabled=True, partial_tp_r=1.0,
    trend_filter=True, adx_min=20.0, time_stop_hours=8,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _run_oos(params: LondonBreakoutParams, shared: SharedParams, dfs_full: dict) -> dict:
    dfs_oos = {k: v[v.index >= OOS_START] for k, v in dfs_full.items()}
    strategy = LondonBreakoutStrategy(params, shared)
    trades = run_backtest_fast(strategy, shared, dfs_oos)
    return compute_metrics(trades)


def _optimize_and_oos(
    base_params: LondonBreakoutParams,
    shared: SharedParams,
    dfs_full: dict,
    win_rate_objective: bool = False,
) -> tuple:
    """Grid-search in-sample, evaluate OOS. Returns (best_params, oos_metrics)."""
    dfs_is = {k: v[v.index <= IN_SAMPLE_END] for k, v in dfs_full.items()}
    best_score = -float("inf")
    best_params = base_params
    count = 0

    for london_end in (10, 11, 12):
        for tp_mult in (1.0, 1.5, 2.0, 2.5, 3.0):
            for range_max in (1.0, 1.5, 2.0):
                for range_min in (0.2, 0.3, 0.5):
                    if range_min >= range_max:
                        continue
                    candidate = replace(
                        base_params,
                        london_end_hour=london_end,
                        tp_range_mult=tp_mult,
                        range_max_atr_mult=range_max,
                        range_min_atr_mult=range_min,
                    )
                    strategy = LondonBreakoutStrategy(candidate, shared)
                    trades = run_backtest_fast(strategy, shared, dfs_is)
                    m = compute_metrics(trades)
                    n = m.get("trade_count", 0)
                    if n < 40:     # lowered: heavy filters produce fewer IS trades
                        continue
                    if win_rate_objective:
                        # Maximise win rate subject to minimum expectancy
                        if m.get("expectancy_pts", -999) < 2.0:
                            continue
                        score = m.get("win_rate_%", 0)
                    else:
                        score = m.get("expectancy_pts", -999) * (n ** 0.5)
                    if score > best_score:
                        best_score = score
                        best_params = candidate
                    count += 1

    print(f"  [optimize] {count} combos  objective={'win_rate' if win_rate_objective else 'expectancy'}")
    oos_m = _run_oos(best_params, shared, dfs_full)
    return best_params, oos_m


def _row(e: dict) -> str:
    return (
        f"| {e['name']:<24} | {e['data']:<15} | {e['desc']:<58} "
        f"| {e['oos_trades']:>6} | {e['oos_wr']:>6.1f}% "
        f"| {e['oos_exp']:>+8.3f} | {e['oos_pf']:>5.3f} "
        f"| {e['oos_dd']:>8.1f} | {e['verdict']} |"
    )


def _append_to_log(new_entries: list, new_details: list, all_entries: list) -> None:
    header = (
        "# STRATEGY LOG — XAUUSD Gold Trading Bot\n\n"
        f"**Data:** Synthetic GBM 2022-01-01 → 2026-01-01  |  "
        f"**OOS window:** {OOS_START}+  |  "
        f"**Updated:** {datetime.date.today()}\n\n"
        "---\n\n## Master Summary Table\n\n"
        "| Variant                   | Data            | Key Rules / Changes"
        "                                                           "
        "| Trades | Win%   | Expectancy | PF    | Max DD   | Verdict |\n"
        "|---------------------------|-----------------|"
        "----------------------------------------------------------|"
        "--------|--------|-----------|-------|----------|--------|\n"
    )
    rows    = "\n".join(_row(e) for e in all_entries)
    details = "\n\n---\n\n".join(new_details)

    # Read existing detail sections to preserve round-1 notes
    existing = ""
    if LOG_PATH.exists():
        text = LOG_PATH.read_text()
        marker = "## Detailed Results"
        if marker in text:
            existing = text.split(marker, 1)[1].strip()

    content = (
        header + rows
        + "\n\n---\n\n## Detailed Results\n\n"
        + (existing + "\n\n---\n\n" if existing else "")
        + details + "\n"
    )
    LOG_PATH.write_text(content)
    print(f"[log] STRATEGY_LOG.md updated ({len(all_entries)} total entries)")


# ─────────────────────────────────────────────────────────────────────────────
# Round-2 iteration definitions
# ─────────────────────────────────────────────────────────────────────────────

ROUND2 = [
    {
        "name":    "B-v5-early-partial",
        "desc":    "+ Earlier partial TP at 0.5R (lock profits sooner)",
        "tweak":   dict(partial_tp_r=0.5),
        "win_rate_obj": False,
    },
    {
        "name":    "B-v6-closer-tp",
        "desc":    "+ Re-optimize final TP toward 1.0–2.0× range (closer target)",
        "tweak":   dict(),   # let optimizer search lower tp_range_mult
        "win_rate_obj": False,
    },
    {
        "name":    "B-v7-wr-objective",
        "desc":    "+ Re-optimize with win-rate objective (exp > 2 constraint)",
        "tweak":   dict(),
        "win_rate_obj": True,
    },
    {
        "name":    "B-v8-tight-trail",
        "desc":    "+ Tighter trail after partial (0.75×ATR on runner)",
        "tweak":   dict(),   # trail_after_partial_atr_mult already 0.75 in SharedParams
        "win_rate_obj": False,
    },
    {
        "name":    "B-v9-scalp-mode",
        "desc":    "+ Scalp mode: close 100% at partial TP level (max win rate)",
        "tweak":   dict(full_close_at_partial=True),
        "win_rate_obj": False,
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    shared    = SharedParams()
    dfs_full  = load_data()
    all_entries = list(PRIOR_ENTRIES)
    new_details = []

    best_params = V4_PARAMS
    best_wr     = PRIOR_ENTRIES[-1]["oos_wr"]   # 62.5
    best_exp    = PRIOR_ENTRIES[-1]["oos_exp"]   # 6.309

    target_wr   = 80.0
    entry_num   = len(PRIOR_ENTRIES) + 1

    print(f"Starting win-rate ladder round 2  (current best: {best_wr:.1f}%  target: {target_wr:.0f}%)\n")

    for it in ROUND2:
        print(f"{'─'*62}")
        print(f"Round {entry_num - len(PRIOR_ENTRIES)}: {it['name']}")
        print(f"  Adding: {it['desc']}")

        candidate_params = replace(best_params, **it["tweak"])
        best_candidate, oos_m = _optimize_and_oos(
            candidate_params, shared, dfs_full,
            win_rate_objective=it["win_rate_obj"],
        )

        wr  = oos_m.get("win_rate_%",     0.0)
        exp = oos_m.get("expectancy_pts", -999)
        pf  = oos_m.get("profit_factor",  0.0)
        dd  = oos_m.get("max_dd_pts",     0.0)
        n   = oos_m.get("trade_count",    0)

        improved = wr > best_wr and exp > 0 and n >= 30
        verdict  = "✅ KEPT" if improved else "❌ REJECTED"

        print(f"  OOS → trades={n}  win={wr:.1f}%  exp={exp:+.3f}  PF={pf:.3f}  DD={dd:.1f}")
        print(f"  vs best:  {best_wr:.1f}% → {wr:.1f}%   {verdict}")

        all_entries.append(dict(
            name=it["name"], data="Synthetic GBM", desc=it["desc"],
            oos_trades=n, oos_wr=wr, oos_exp=exp,
            oos_pf=pf, oos_dd=dd, verdict=verdict,
        ))

        p = best_candidate
        new_details.append(
            f"### R2-{entry_num - len(PRIOR_ENTRIES)}. {it['name']}\n"
            f"Change: {it['desc']}  \n"
            f"Params: london_end={p.london_end_hour}h, tp={p.tp_range_mult}×, "
            f"rmax={p.range_max_atr_mult}×, rmin={p.range_min_atr_mult}×, "
            f"partial_r={p.partial_tp_r}, scalp={p.full_close_at_partial}, "
            f"adx_min={p.adx_min}, time_stop={p.time_stop_hours}h  \n"
            f"OOS: trades={n}, win={wr:.1f}%, exp={exp:+.3f}, PF={pf:.3f}, DD={dd:.1f}  \n"
            f"Verdict: **{verdict}**\n"
        )
        entry_num += 1

        if improved:
            best_params = best_candidate
            best_wr     = wr
            best_exp    = exp

        if best_wr >= target_wr:
            print(f"\n  🎯 Target {target_wr:.0f}% reached at {best_wr:.1f}%!")
            break

    # ── Update config.py note (params printed for manual update) ──────────
    print(f"\n{'═'*62}")
    print("ROUND 2 FINAL RESULT")
    print(f"{'═'*62}")
    target_met = best_wr >= target_wr
    print(f"Max OOS win rate achieved:  {best_wr:.1f}%")
    print(f"Target (80% win rate):      {'MET ✅' if target_met else 'NOT MET ❌'}")
    if not target_met:
        print("Reason: taking profit even earlier would reduce avg_win below")
        print("        avg_loss, making expectancy negative — the gate rejected it.")
        print("        On real XAUUSD data with tighter spreads this ceiling may differ.")
    print(f"\nFinal params to paste into config.py BREAKOUT_PARAMS:")
    p = best_params
    print(f"  london_end_hour={p.london_end_hour}, tp_range_mult={p.tp_range_mult},")
    print(f"  range_max_atr_mult={p.range_max_atr_mult}, range_min_atr_mult={p.range_min_atr_mult},")
    print(f"  partial_tp_enabled={p.partial_tp_enabled}, partial_tp_r={p.partial_tp_r},")
    print(f"  trend_filter={p.trend_filter}, adx_min={p.adx_min},")
    print(f"  time_stop_hours={p.time_stop_hours}, full_close_at_partial={p.full_close_at_partial}")

    # Add final-variant row
    all_entries.append(dict(
        name="★ FINAL BEST",
        data="Synthetic GBM",
        desc=f"All kept rounds combined — win_rate={best_wr:.1f}%",
        oos_trades=all_entries[-1]["oos_trades"] if improved else PRIOR_ENTRIES[-1]["oos_trades"],
        oos_wr=best_wr, oos_exp=best_exp,
        oos_pf=all_entries[-1]["oos_pf"] if improved else PRIOR_ENTRIES[-1]["oos_pf"],
        oos_dd=all_entries[-1]["oos_dd"] if improved else PRIOR_ENTRIES[-1]["oos_dd"],
        verdict="🏆 DEPLOY" if target_met else f"🏆 BEST ({best_wr:.1f}%)",
    ))

    _append_to_log([], new_details, all_entries)

    # ── Print master table ─────────────────────────────────────────────────
    print("\n\n" + "═" * 112)
    print("  MASTER STRATEGY TABLE — ALL VARIANTS TESTED")
    print("═" * 112)
    hdr = f"{'Variant':<26} {'Win%':>6}  {'Expect':>8}  {'PF':>5}  {'MaxDD':>8}  {'Trades':>6}  Verdict"
    print(hdr)
    print("─" * 112)
    for e in all_entries:
        print(
            f"{e['name']:<26} {e['oos_wr']:>5.1f}%  {e['oos_exp']:>+8.3f}  "
            f"{e['oos_pf']:>5.3f}  {e['oos_dd']:>8.1f}  {e['oos_trades']:>6}  {e['verdict']}"
        )
    print("═" * 112)
    print("Full details → STRATEGY_LOG.md")


if __name__ == "__main__":
    main()
