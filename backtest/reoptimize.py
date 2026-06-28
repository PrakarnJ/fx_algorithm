"""
Auto re-optimize REGIME_PARAMS for the regime-aware strategy.

Pipeline (propose-and-confirm — never touches the live config until --apply):
  1. download  : fetch latest Dukascopy bars, merge into data/XAUUSD_*.csv
  2. optimize  : Optuna search on the most recent 12 months
  3. validate  : walk-forward sanity check (does the method still hold?)
  4. propose   : write campaign_runs/reoptimize_proposal.json (old vs new + metrics)

Apply the proposed params (writes data/regime_params.json, which config.py reads):
  python backtest/reoptimize.py --apply

Install a monthly schedule (macOS/Linux cron):
  python backtest/reoptimize.py --install-cron

Run the full pipeline now:
  python backtest/reoptimize.py            [--no-download] [--trials N] [--wf-trials N]

Progress is streamed to campaign_runs/reoptimize_status.json so a UI can poll it.
"""
import sys
import json
import time
import shutil
import argparse
import datetime
import subprocess
from pathlib import Path
from dataclasses import asdict, replace

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import optuna

from config import SHARED, RegimeSwitchParams, REGIME_PARAMS
from backtest.engine import load_data
from backtest.walkforward import (
    evaluate, score, suggest_regime, FAMILIES, walk_forward,
)

optuna.logging.set_verbosity(optuna.logging.WARNING)

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
RUN_DIR = ROOT / "backtest" / "campaign_runs"
STATUS = RUN_DIR / "reoptimize_status.json"
PROPOSAL = RUN_DIR / "reoptimize_proposal.json"
OVERRIDE = DATA_DIR / "regime_params.json"

OPT_MONTHS = 12          # optimize on the most recent N months
SYMBOL_DUKA = "xauusd"
TF_DUKA = {"m15": "M15", "h1": "H1", "h4": "H4"}


# ───────────────────────── status streaming ─────────────────────────

def set_status(stage, pct, message, **extra):
    RUN_DIR.mkdir(exist_ok=True)
    payload = {"stage": stage, "pct": pct, "message": message,
               "running": stage not in ("done", "error"),
               "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               **extra}
    tmp = STATUS.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=1, default=str))
    tmp.replace(STATUS)
    print(f"[{stage}] {pct}% {message}", flush=True)


# ───────────────────────── 1. download + merge ─────────────────────────

def download_and_merge(days_back: int = 150) -> None:
    """Download the recent slice from Dukascopy and merge into data/XAUUSD_*.csv,
    preserving full history (dedupe by timestamp)."""
    tmp = RUN_DIR / "_duka_tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    today = datetime.date.today()
    frm = (today - datetime.timedelta(days=days_back)).isoformat()
    to = (today + datetime.timedelta(days=1)).isoformat()

    for tf_in, tf_out in TF_DUKA.items():
        set_status("download", 5, f"downloading {tf_out} ({frm}→{to})")
        cmd = ["npx", "-y", "dukascopy-node", "-i", SYMBOL_DUKA,
               "-from", frm, "-to", to, "-t", tf_in, "-f", "csv",
               "-dir", str(tmp), "-r", "5", "-rp", "800"]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=600)
        except Exception as e:
            set_status("download", 8, f"{tf_out} download skipped ({type(e).__name__}); using existing data")
            continue
        _merge_tf(tmp, tf_in, tf_out)
    shutil.rmtree(tmp, ignore_errors=True)


def _merge_tf(tmp: Path, tf_in: str, tf_out: str) -> None:
    matches = sorted(tmp.glob(f"{SYMBOL_DUKA}-{tf_in}-*.csv"))
    if not matches:
        return
    new = pd.read_csv(matches[-1])
    if new.empty:
        return
    new["time"] = pd.to_datetime(new["timestamp"], unit="ms", utc=True)
    new = new.set_index("time")[["open", "high", "low", "close"]]
    new = new[~((new["high"] == new["low"]) & (new["open"] == new["close"]))]
    new = new[new.index.dayofweek < 5]

    existing_path = DATA_DIR / f"XAUUSD_{tf_out}.csv"
    if existing_path.exists():
        old = pd.read_csv(existing_path, index_col="time", parse_dates=True)
        merged = pd.concat([old, new])
        merged = merged[~merged.index.duplicated(keep="last")].sort_index()
    else:
        merged = new.sort_index()
    merged.to_csv(existing_path)


# ───────────────────────── 2. optimize ─────────────────────────

def optimize_recent(dfs, n_trials: int):
    h1 = dfs["H1"]
    end = h1.index[-1]
    start = end - pd.DateOffset(months=OPT_MONTHS)
    tr_start, tr_end = str(start.date()), str((end + pd.Timedelta(days=1)).date())
    fam = FAMILIES["regime_switch"]

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(multivariate=True, seed=42))
    last = [time.time()]

    def obj(trial):
        p = suggest_regime(trial)
        m, _ = evaluate(p, fam, dfs, tr_start, tr_end)
        if time.time() - last[0] > 5:
            last[0] = time.time()
            set_status("optimize", 35,
                       f"optimizing on {tr_start}→{tr_end}: trial {trial.number}/{n_trials}")
        return score(m)

    study.optimize(obj, n_trials=n_trials, catch=(Exception,))
    best = RegimeSwitchParams(**{**asdict(RegimeSwitchParams()), **study.best_params})
    m, _ = evaluate(best, fam, dfs, tr_start, tr_end)
    return best, m, (tr_start, tr_end)


# ───────────────────────── 3. validate (walk-forward) ─────────────────────────

def validate_wf(dfs, wf_trials: int):
    set_status("validate", 70, f"walk-forward sanity check ({wf_trials} trials/window)…")
    res = walk_forward("regime_switch", wf_trials, dfs)
    return res["aggregate"]


# ───────────────────────── pipeline ─────────────────────────

def run_pipeline(download: bool, trials: int, wf_trials: int) -> dict:
    t0 = time.time()
    set_status("start", 0, "starting re-optimization")
    if download:
        download_and_merge()

    set_status("optimize", 20, "loading data + optimizing")
    dfs = load_data()
    best, opt_metrics, window = optimize_recent(dfs, trials)

    wf_metrics = validate_wf(dfs, wf_trials)

    pf = wf_metrics.get("profit_factor")
    recommend = bool(
        wf_metrics.get("trade_count", 0) >= 20
        and pf is not None and pf > 1.2
        and wf_metrics.get("expectancy_pips", 0) > 0
    )
    proposal = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "optimize_window": window,
        "current_params": asdict(REGIME_PARAMS),
        "new_params": asdict(best),
        "optimize_metrics": _clean(opt_metrics),
        "walkforward_metrics": _clean(wf_metrics),
        "recommend": recommend,
        "elapsed_s": round(time.time() - t0),
        "data_end": str(dfs["H1"].index[-1].date()),
    }
    PROPOSAL.write_text(json.dumps(proposal, indent=1, default=str))
    verdict = "RECOMMENDED" if recommend else "NOT recommended (walk-forward weak)"
    set_status("done", 100, f"proposal ready — {verdict}",
               recommend=recommend, proposal_ready=True)
    return proposal


def _clean(m: dict) -> dict:
    out = {}
    for k, v in (m or {}).items():
        if isinstance(v, (np.floating, np.integer)):
            v = float(v)
        if isinstance(v, float) and not np.isfinite(v):
            v = None
        out[k] = v
    return out


# ───────────────────────── apply / cron ─────────────────────────

def apply_proposal() -> dict:
    if not PROPOSAL.exists():
        raise SystemExit("No proposal found — run re-optimization first.")
    proposal = json.loads(PROPOSAL.read_text())
    DATA_DIR.mkdir(exist_ok=True)
    payload = {
        **proposal["new_params"],
        "_last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "_source": "reoptimize",
    }
    OVERRIDE.write_text(json.dumps(payload, indent=1))
    print(f"Applied → {OVERRIDE}")
    print("Params applied — config.py reads the override on next import.")
    return proposal["new_params"]


def install_cron() -> None:
    py = sys.executable
    script = str(Path(__file__).resolve())
    log = str(RUN_DIR / "reoptimize_cron.log")
    line = f"0 6 1 * * cd {ROOT} && {py} {script} >> {log} 2>&1  # regime reoptimize (monthly)"
    print("Add this line to your crontab (run: crontab -e):\n")
    print("  " + line)
    print("\nIt runs at 06:00 on the 1st of each month: download → optimize → propose.")
    print("Proposals are NOT auto-applied — review in the dashboard, then click Apply.")
    print("\n(Windows: use Task Scheduler to run the same command monthly.)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-download", action="store_true", help="skip Dukascopy download")
    ap.add_argument("--trials", type=int, default=60)
    ap.add_argument("--wf-trials", type=int, default=20)
    ap.add_argument("--apply", action="store_true", help="apply the latest proposal to live config")
    ap.add_argument("--install-cron", action="store_true")
    args = ap.parse_args()

    if args.install_cron:
        install_cron()
        return
    if args.apply:
        apply_proposal()
        return

    try:
        p = run_pipeline(not args.no_download, args.trials, args.wf_trials)
        wf = p["walkforward_metrics"]
        print(f"\nProposal: WF PF={wf.get('profit_factor')} "
              f"trades={wf.get('trade_count')} total={wf.get('total_profit_pips')}pts "
              f"→ {'RECOMMENDED' if p['recommend'] else 'not recommended'}")
        print(f"Review + apply: python backtest/reoptimize.py --apply  (or use the dashboard)")
    except Exception as e:
        set_status("error", 0, f"failed: {e}")
        raise


if __name__ == "__main__":
    main()
