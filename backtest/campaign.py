"""
Time-budgeted strategy-optimization campaign.

Searches four strategy families with Optuna (TPE), using an honest
three-way split, then Monte-Carlo robustness gates on the finalists:

  TRAIN  2022-01-01 → 2023-12-31   Optuna objective (selection only)
  VAL    2024-01-01 → 2024-12-31   ranking of top trials
  OOS    2025-01-01 → end          finalists only, hard-capped evaluations

  (ML family: model fitted on 2022-01 → 2023-06; objective scored on the
   out-of-fit tail 2023-07 → 2023-12 to avoid in-fit inflation.)

Targets: win rate >= 90%, profit factor > 2.0, max DD < 10 pts, >= 30 trades.
Feasibility score = min(WR/90, min(PF,4)/2, 10/DD); >= 1.0 iff all targets met.

Checkpoints to backtest/campaign_runs/checkpoint.json after every family and
uses Optuna JournalStorage, so --resume continues where it stopped.

Run:  python backtest/campaign.py --budget-hours 8
      python backtest/campaign.py --budget-hours 0.1 --trials-cap 10   # dry run
      python backtest/campaign.py --budget-hours 8 --resume
"""
import sys
import json
import time
import argparse
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dataclasses import asdict
import numpy as np

import optuna
from optuna.samplers import TPESampler

from config import (
    SharedParams, LondonBreakoutParams,
    MeanReversionParams, RsiFadeParams, MLClassifierParams,
)
from algorithms.london_breakout import LondonBreakoutStrategy
from algorithms.mean_reversion import MeanReversionStrategy
from algorithms.rsi_fade import RsiFadeStrategy
from algorithms.ml_classifier import MLClassifierStrategy
from backtest.engine import load_data, run_backtest_fast
from backtest.metrics import compute_metrics
from backtest.montecarlo import run_monte_carlo, mc_passes_targets

optuna.logging.set_verbosity(optuna.logging.WARNING)

RUN_DIR = Path(__file__).parent / "campaign_runs"
CHECKPOINT = RUN_DIR / "checkpoint.json"
RESULTS = RUN_DIR / "campaign_results.json"
LOG_PATH = Path(__file__).parent.parent / "STRATEGY_LOG.md"

TRAIN = ("2022-01-01", "2023-12-31")
VAL = ("2024-01-01", "2024-12-31")
OOS = ("2025-01-01", "2099-01-01")
ML_FIT_END = "2023-06-30"
ML_TRAIN = ("2023-07-01", "2023-12-31")     # out-of-fit objective window

TARGETS = {"wr": 90.0, "pf": 2.0, "dd": 10.0, "min_trades": 30}
GATE_PF_MIN = 1.3                            # secondary: project acceptance gate
TOP_TRAIN, TOP_VAL, MAX_OOS_EVALS = 20, 3, 8

SHARED = SharedParams()


# ───────────────────────── scoring / evaluation ─────────────────────────

def feasibility_score(m: dict) -> float:
    n = m.get("trade_count", 0)
    if n < TARGETS["min_trades"]:
        return -1.0 + 0.9 * n / TARGETS["min_trades"]
    if m.get("expectancy_pips", -1) <= 0:
        return 0.0
    pf = m.get("profit_factor")
    pf = 4.0 if pf is None or not np.isfinite(pf) else min(pf, 4.0)
    return min(
        m["win_rate_%"] / TARGETS["wr"],
        pf / TARGETS["pf"],
        TARGETS["dd"] / max(m["max_dd_pips"], 1e-6),
    )


def hits_targets(m: dict) -> bool:
    pf = m.get("profit_factor")
    pf_ok = pf is None or pf > TARGETS["pf"]
    return (
        m.get("trade_count", 0) >= TARGETS["min_trades"]
        and m.get("win_rate_%", 0) >= TARGETS["wr"]
        and pf_ok
        and m.get("max_dd_pips", 1e9) < TARGETS["dd"]
    )


def run_window(strategy, dfs_full: dict, start: str, end: str) -> dict:
    """Backtest with a 30-day warmup buffer; metrics only on trades inside
    [start, end] so the window is exact (no warmup burn)."""
    buf = str(np.datetime64(start) - np.timedelta64(30, "D"))
    dfs = {k: v[(v.index >= buf) & (v.index <= end)] for k, v in dfs_full.items()}
    exec_tf = getattr(strategy, "exec_tf", "H1")
    if len(dfs[exec_tf]) < 1100:
        return {"metrics": {"trade_count": 0}, "profits": []}
    trades = run_backtest_fast(strategy, SHARED, dfs, exec_tf=exec_tf)
    trades = [t for t in trades if str(t.entry_time) >= start]
    m = compute_metrics(trades)
    if m.get("profit_factor") == float("inf"):
        m["profit_factor"] = None
    return {"metrics": m, "profits": [t.profit_pts for t in trades]}


# ───────────────────────── family definitions ─────────────────────────

def suggest_mr(trial) -> MeanReversionParams:
    return MeanReversionParams(
        tf=trial.suggest_categorical("tf", ["M15", "H1"]),
        z_lookback=trial.suggest_int("z_lookback", 20, 120, step=10),
        z_entry=trial.suggest_float("z_entry", 1.2, 3.5, step=0.1),
        rsi_confirm=trial.suggest_categorical("rsi_confirm", [True, False]),
        rsi_period=trial.suggest_int("rsi_period", 2, 6),
        rsi_extreme=trial.suggest_float("rsi_extreme", 10, 35, step=5),
        tp_pts=trial.suggest_float("tp_pts", 1.5, 10.0, step=0.5),
        sl_pts=trial.suggest_float("sl_pts", 4.0, 25.0, step=1.0),
        cooldown_bars=trial.suggest_int("cooldown_bars", 2, 48),
        time_stop_hours=trial.suggest_int("time_stop_hours", 0, 16, step=2),
        session_start=trial.suggest_categorical("session_start", [0, 6, 12]),
        session_end=trial.suggest_categorical("session_end", [24, 17, 21]),
        manage_trail=trial.suggest_categorical("manage_trail", [True, False]),
    )


def suggest_rsi(trial) -> RsiFadeParams:
    return RsiFadeParams(
        tf=trial.suggest_categorical("tf", ["M15", "H1"]),
        rsi_period=trial.suggest_int("rsi_period", 2, 8),
        buy_below=trial.suggest_float("buy_below", 4, 30, step=2),
        sell_above=trial.suggest_float("sell_above", 70, 96, step=2),
        trend_gate=trial.suggest_categorical("trend_gate", [True, False]),
        tp_pts=trial.suggest_float("tp_pts", 1.5, 10.0, step=0.5),
        sl_pts=trial.suggest_float("sl_pts", 4.0, 25.0, step=1.0),
        cooldown_bars=trial.suggest_int("cooldown_bars", 2, 48),
        time_stop_hours=trial.suggest_int("time_stop_hours", 0, 16, step=2),
        manage_trail=trial.suggest_categorical("manage_trail", [True, False]),
    )


def suggest_breakout(trial) -> LondonBreakoutParams:
    rmin = trial.suggest_float("range_min_atr_mult", 0.1, 0.5, step=0.1)
    rmax = trial.suggest_float("range_max_atr_mult", 1.0, 2.5, step=0.5)
    return LondonBreakoutParams(
        london_end_hour=trial.suggest_int("london_end_hour", 9, 13),
        entry_buffer_atr_mult=trial.suggest_float("entry_buffer_atr_mult", 0.05, 0.3, step=0.05),
        range_max_atr_mult=rmax,   # rmin <= 0.5 < rmax always — no overlap possible
        range_min_atr_mult=rmin,
        tp_range_mult=trial.suggest_float("tp_range_mult", 0.5, 3.5, step=0.25),
        partial_tp_enabled=trial.suggest_categorical("partial_tp_enabled", [True, False]),
        partial_tp_r=trial.suggest_float("partial_tp_r", 0.3, 1.5, step=0.1),
        trend_filter=trial.suggest_categorical("trend_filter", [True, False]),
        adx_min=trial.suggest_float("adx_min", 0, 30, step=5),
        time_stop_hours=trial.suggest_int("time_stop_hours", 0, 12, step=2),
        full_close_at_partial=trial.suggest_categorical("full_close_at_partial", [True, False]),
    )


def suggest_ml(trial) -> MLClassifierParams:
    return MLClassifierParams(
        tf="M15",
        tp_pts=trial.suggest_float("tp_pts", 1.5, 8.0, step=0.5),
        sl_pts=trial.suggest_float("sl_pts", 4.0, 20.0, step=1.0),
        horizon_bars=trial.suggest_int("horizon_bars", 8, 64, step=8),
        threshold=trial.suggest_float("threshold", 0.55, 0.95, step=0.025),
        cooldown_bars=trial.suggest_int("cooldown_bars", 2, 48),
        time_stop_hours=trial.suggest_int("time_stop_hours", 0, 16, step=4),
        max_depth=trial.suggest_int("max_depth", 3, 7),
        learning_rate=trial.suggest_float("learning_rate", 0.03, 0.2, log=True),
        max_iter=trial.suggest_int("max_iter", 100, 400, step=50),
        min_samples_leaf=trial.suggest_int("min_samples_leaf", 20, 150, step=10),
        l2_regularization=trial.suggest_float("l2_regularization", 0.0, 3.0, step=0.5),
    )


def build_plain(cls):
    def _build(params, dfs_full):
        return cls(params, SHARED)
    return _build


def build_ml(params, dfs_full):
    dfs_fit = {k: v[v.index <= ML_FIT_END] for k, v in dfs_full.items()}
    return MLClassifierStrategy(params, SHARED).fit(dfs_fit)


FAMILIES = [
    dict(name="breakout", suggest=suggest_breakout, params_cls=LondonBreakoutParams,
         build=build_plain(LondonBreakoutStrategy), hours=1.0, train=TRAIN),
    dict(name="mean_reversion", suggest=suggest_mr, params_cls=MeanReversionParams,
         build=build_plain(MeanReversionStrategy), hours=2.5, train=TRAIN),
    dict(name="rsi_fade", suggest=suggest_rsi, params_cls=RsiFadeParams,
         build=build_plain(RsiFadeStrategy), hours=1.0, train=TRAIN),
    dict(name="ml", suggest=suggest_ml, params_cls=MLClassifierParams,
         build=build_ml, hours=2.0, train=ML_TRAIN),
]
REFINE_HOURS = 1.3


# ───────────────────────── orchestration ─────────────────────────

def load_state(resume: bool) -> dict:
    if resume and CHECKPOINT.exists():
        return json.loads(CHECKPOINT.read_text())
    return {"families": {}, "oos_evals": [], "elapsed_committed_s": 0.0,
            "started": datetime.datetime.now(datetime.timezone.utc).isoformat()}


def save_state(state: dict) -> None:
    RUN_DIR.mkdir(exist_ok=True)
    tmp = CHECKPOINT.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1, default=str))
    tmp.replace(CHECKPOINT)


def make_storage():
    RUN_DIR.mkdir(exist_ok=True)
    try:
        from optuna.storages.journal import JournalStorage, JournalFileBackend
        return JournalStorage(JournalFileBackend(str(RUN_DIR / "optuna_journal.log")))
    except ImportError:
        from optuna.storages import JournalStorage, JournalFileStorage
        return JournalStorage(JournalFileStorage(str(RUN_DIR / "optuna_journal.log")))


def run_family(fam: dict, dfs_full: dict, storage, timeout_s: float,
               trials_cap: int, state: dict) -> None:
    name = fam["name"]
    study = optuna.create_study(
        study_name=name, storage=storage, direction="maximize",
        sampler=TPESampler(multivariate=True, group=True, seed=42),
        load_if_exists=True,
    )
    last_beat = [time.time()]

    def objective(trial):
        params = fam["suggest"](trial)
        strategy = fam["build"](params, dfs_full)
        res = run_window(strategy, dfs_full, *fam["train"])
        score = feasibility_score(res["metrics"])
        trial.set_user_attr("train_metrics", res["metrics"])
        if time.time() - last_beat[0] > 60:
            last_beat[0] = time.time()
            try:
                best = f"{study.best_value:.3f}"
            except ValueError:
                best = "n/a"
            print(f"[{name}] trial {trial.number}  best={best} "
                  f"({datetime.datetime.now():%H:%M:%S})", flush=True)
        return score

    n_before = len(study.trials)
    if timeout_s > 10:
        study.optimize(objective, n_trials=trials_cap, timeout=timeout_s,
                       catch=(Exception,))
    if study.trials:
        try:
            best = f"{study.best_value:.3f}"
        except ValueError:
            best = "n/a"
        print(f"[{name}] {len(study.trials) - n_before} new trials "
              f"({len(study.trials)} total), best TRAIN score {best}", flush=True)
    else:
        print(f"[{name}] no trials", flush=True)

    # Selection: top-20 TRAIN → evaluate VAL → keep top-3
    done = [t for t in study.trials if t.value is not None]
    done.sort(key=lambda t: t.value, reverse=True)
    top_val = []
    seen = set()
    for t in done[:TOP_TRAIN]:
        key = json.dumps(t.params, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        params = fam["params_cls"](**{**asdict(fam["params_cls"]()), **t.params})
        strategy = fam["build"](params, dfs_full)
        res = run_window(strategy, dfs_full, *VAL)
        vs = feasibility_score(res["metrics"])
        top_val.append({
            "params": asdict(params), "train_score": round(t.value, 4),
            "val_score": round(vs, 4), "val_metrics": res["metrics"],
            "val_mc": run_monte_carlo(res["profits"]) if res["profits"] else None,
        })
    top_val.sort(key=lambda c: c["val_score"], reverse=True)
    state["families"][name] = {
        "status": "done", "trials": len(study.trials),
        "best_train_score": round(study.best_value, 4) if done else None,
        "top_val": top_val[:TOP_VAL],
    }
    save_state(state)


def final_phase(state: dict, dfs_full: dict) -> dict:
    """OOS evaluation + Monte Carlo on the global top candidates."""
    candidates = []
    for fname, fdata in state["families"].items():
        fam = next(f for f in FAMILIES if f["name"] == fname)
        for c in fdata.get("top_val", []):
            candidates.append({**c, "family": fname, "fam": fam})
    candidates.sort(key=lambda c: c["val_score"], reverse=True)

    results = []
    for c in candidates[:MAX_OOS_EVALS]:
        params = c["fam"]["params_cls"](**c["params"])
        strategy = c["fam"]["build"](params, dfs_full)
        res = run_window(strategy, dfs_full, *OOS)
        m = res["metrics"]
        mc = run_monte_carlo(res["profits"]) if res["profits"] else {"valid": False}
        mc_gate = mc_passes_targets(mc, TARGETS["wr"], TARGETS["pf"], TARGETS["dd"])
        entry = {
            "family": c["family"], "params": c["params"],
            "val_score": c["val_score"], "val_metrics": c["val_metrics"],
            "oos_metrics": m, "oos_score": round(feasibility_score(m), 4),
            "oos_mc": mc, "mc_gate": mc_gate,
            "targets_met": hits_targets(m) and mc_gate["passed"],
        }
        results.append(entry)
        state["oos_evals"].append({
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "family": c["family"], "oos_metrics": m,
        })
        wr = m.get("win_rate_%", 0)
        print(f"[OOS] {c['family']:<15} trades={m.get('trade_count',0):>4} "
              f"wr={wr:>5.1f}% pf={m.get('profit_factor')} "
              f"dd={m.get('max_dd_pips')} score={entry['oos_score']}", flush=True)
    save_state(state)
    return {"finalists": results}


def write_report(state: dict, final: dict, budget_hours: float) -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    lines = [
        "\n\n---\n",
        f"## Campaign {now:%Y-%m-%d %H:%M} UTC — Optuna + Monte Carlo "
        f"({budget_hours:.1f}h budget, real Dukascopy data)\n",
        f"**Targets:** WR ≥ {TARGETS['wr']:.0f}%, PF > {TARGETS['pf']}, "
        f"max DD < {TARGETS['dd']:.0f} pts, ≥ {TARGETS['min_trades']} trades  ",
        f"**Splits:** TRAIN {TRAIN[0]}→{TRAIN[1]} · VAL {VAL[0]}→{VAL[1]} · "
        f"OOS {OOS[0]}+ · ML fit ≤ {ML_FIT_END}  ",
        f"**OOS evaluations this run:** {len(final['finalists'])} "
        f"(selection bias grows with every OOS look)\n",
        "| Family | Trials | VAL score | OOS trades | OOS WR | OOS exp | OOS PF "
        "| OOS DD | MC p5 WR | MC p95 DD | Targets |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in final["finalists"]:
        m, mc = r["oos_metrics"], r["oos_mc"]
        b = mc.get("bootstrap", {}) if mc.get("valid") else {}
        trials = state["families"][r["family"]]["trials"]
        lines.append(
            f"| {r['family']} | {trials} | {r['val_score']:.3f} "
            f"| {m.get('trade_count', 0)} | {m.get('win_rate_%', 0):.1f}% "
            f"| {m.get('expectancy_pips', 0):+.2f} | {m.get('profit_factor')} "
            f"| {m.get('max_dd_pips', 0):.1f} "
            f"| {b.get('win_rate_%', {}).get('p5', '—')} "
            f"| {b.get('max_dd_pips', {}).get('p95', '—')} "
            f"| {'✅ MET' if r['targets_met'] else '❌'} |"
        )
    met = [r for r in final["finalists"] if r["targets_met"]]
    if met:
        best = met[0]
        lines.append(f"\n**TARGETS MET** by `{best['family']}` — params: "
                     f"`{json.dumps(best['params'])}`")
    else:
        best = max(final["finalists"], key=lambda r: r["oos_score"], default=None)
        lines.append(
            "\n**TARGETS NOT MET.** "
            + (f"Closest: `{best['family']}` (OOS feasibility {best['oos_score']:.3f}, "
               f"binding constraint = lowest of WR/90, PF/2, 10/DD). "
               if best else "No viable finalists. ")
            + "90% WR with PF>2 and DD<10pts demands a TP:SL shape and consistency "
              "that the searched families could not sustain out-of-sample."
        )
    with open(LOG_PATH, "a") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[log] report appended to {LOG_PATH.name}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget-hours", type=float, default=8.0)
    ap.add_argument("--trials-cap", type=int, default=100000)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    deadline = t0 + args.budget_hours * 3600
    RUN_DIR.mkdir(exist_ok=True)
    if not (args.resume and (RUN_DIR / "started_at").exists()):
        (RUN_DIR / "started_at").write_text(str(t0))   # stable start for the monitor
    state = load_state(args.resume)
    dfs_full = load_data()
    h1 = dfs_full["H1"]
    print(f"Campaign start. Data: {h1.index[0]:%Y-%m-%d} → {h1.index[-1]:%Y-%m-%d} "
          f"({len(h1):,} H1 bars). Budget {args.budget_hours}h.", flush=True)

    storage = make_storage()
    total_planned = sum(f["hours"] for f in FAMILIES) + REFINE_HOURS
    scale = (args.budget_hours * 0.95) / total_planned
    reserve = min(600.0, args.budget_hours * 3600 * 0.05)

    for fam in FAMILIES:
        if state["families"].get(fam["name"], {}).get("status") == "done" and args.resume:
            print(f"[{fam['name']}] already done — skipping", flush=True)
            continue
        budget = min(fam["hours"] * 3600 * scale, deadline - time.time() - reserve)
        print(f"\n═══ Family: {fam['name']}  ({budget/3600:.2f}h) ═══", flush=True)
        run_family(fam, dfs_full, storage, budget, args.trials_cap, state)

    # Refinement: extend the family with the best VAL score using leftover time
    remaining = deadline - time.time() - reserve
    if remaining > 600 and state["families"]:
        best_fam_name = max(
            state["families"],
            key=lambda n: (state["families"][n]["top_val"][0]["val_score"]
                           if state["families"][n].get("top_val") else -9),
        )
        fam = next(f for f in FAMILIES if f["name"] == best_fam_name)
        print(f"\n═══ Refinement: {best_fam_name}  ({remaining/3600:.2f}h) ═══", flush=True)
        run_family(fam, dfs_full, storage, remaining, args.trials_cap, state)

    print("\n═══ Final phase: OOS + Monte Carlo ═══", flush=True)
    final = final_phase(state, dfs_full)
    RESULTS.write_text(json.dumps(final, indent=1, default=str))
    write_report(state, final, args.budget_hours)

    state["elapsed_committed_s"] = time.time() - t0
    save_state(state)
    met = any(r["targets_met"] for r in final["finalists"])
    print(f"\nCampaign complete in {(time.time()-t0)/3600:.2f}h. "
          f"Targets {'MET ✅' if met else 'NOT MET ❌'}. "
          f"Results → {RESULTS}", flush=True)


if __name__ == "__main__":
    main()
