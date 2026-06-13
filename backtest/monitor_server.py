"""
Live campaign monitor — a tiny read-only web UI.

Parses the artifacts that backtest/campaign.py already writes
(campaign.out, checkpoint.json, campaign_results.json) and serves a
self-refreshing dashboard. Read-only: it never touches the running
campaign's files except to read them.

Run:  python backtest/monitor_server.py [--port 8770]
Then open http://localhost:8770
"""
import re
import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RUN_DIR = Path(__file__).parent / "campaign_runs"
OUT = RUN_DIR / "campaign.out"
CHECKPOINT = RUN_DIR / "checkpoint.json"
RESULTS = RUN_DIR / "campaign_results.json"
HTML = Path(__file__).parent.parent / "report" / "campaign.html"

FAMILY_ORDER = ["breakout", "mean_reversion", "rsi_fade", "ml"]

RE_START = re.compile(r"Campaign start\. Data: (.+?) → (.+?) \((\S+) H1 bars\)\. Budget ([\d.]+)h")
RE_HEADER = re.compile(r"═══ (Family|Refinement): (\w+)\s+\(([\d.-]+)h\) ═══")
RE_BEAT = re.compile(r"\[(\w+)\] trial (\d+)\s+best=(\S+) \((\d+:\d+:\d+)\)")
RE_DONE = re.compile(r"\[(\w+)\] (\d+) new trials \((\d+) total\), best TRAIN score (\S+)")
RE_NOTRIALS = re.compile(r"\[(\w+)\] no trials")
RE_OOS = re.compile(r"\[OOS\] (\S+)\s+trades=\s*(\d+) wr=\s*([\d.]+)% pf=(\S+) dd=(\S+) score=(\S+)")
RE_FINAL = re.compile(r"═══ Final phase")
RE_COMPLETE = re.compile(r"Campaign complete in ([\d.]+)h\. Targets (MET|NOT MET)")


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except FileNotFoundError:
        return ""


def _load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def build_status() -> dict:
    text = _read(OUT)
    lines = [l for l in text.splitlines() if "optuna_warn" not in l and l.strip()]

    status = {
        "running": True, "phase": "starting", "verdict": None,
        "data": None, "budget_h": None,
        "elapsed_s": None, "start_iso": None,
        "families": {}, "refinement": None,
        "heartbeat": {}, "finalists": [], "log_tail": lines[-30:],
        "now_iso": datetime.now(timezone.utc).isoformat(),
    }

    # Stable start time: sidecar written at launch (file ctime is unreliable —
    # it updates on every append). Fall back to the OUT ctime only if absent.
    started_file = RUN_DIR / "started_at"
    if started_file.exists():
        start_ts = float(started_file.read_text().strip())
    elif OUT.exists():
        start_ts = os.stat(OUT).st_ctime
    else:
        start_ts = None
    if start_ts:
        status["start_iso"] = datetime.fromtimestamp(start_ts, timezone.utc).isoformat()
        status["elapsed_s"] = round(datetime.now().timestamp() - start_ts)

    for l in lines:
        m = RE_START.search(l)
        if m:
            status["data"] = f"{m.group(1)} → {m.group(2)} ({m.group(3)} H1 bars)"
            status["budget_h"] = float(m.group(4))

    # Per-family state machine
    fam = {f: {"status": "pending", "alloc_h": None, "trials": 0,
               "best_train": None, "label": f} for f in FAMILY_ORDER}
    current = None
    refinement = None
    for l in lines:
        m = RE_HEADER.search(l)
        if m:
            kind, name, alloc = m.group(1), m.group(2), float(m.group(3))
            if kind == "Family":
                if name in fam:
                    fam[name]["status"] = "running"
                    fam[name]["alloc_h"] = alloc
                current = ("family", name)
            else:  # Refinement
                refinement = {"family": name, "alloc_h": alloc, "status": "running",
                              "trials_added": 0, "best_train": None}
                current = ("refine", name)
            status["phase"] = f"{kind.lower()}: {name}"
            continue
        m = RE_BEAT.search(l)
        if m:
            name, trial, best = m.group(1), int(m.group(2)), m.group(3)
            status["heartbeat"][name] = {"trial": trial, "best": best, "at": m.group(4)}
            if name in fam and fam[name]["status"] == "running":
                fam[name]["trials"] = trial
            continue
        m = RE_DONE.search(l)
        if m:
            name, added, total, best = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
            if current and current[0] == "refine" and refinement:
                refinement["status"] = "done"
                refinement["trials_added"] = added
                refinement["best_train"] = best
            if name in fam:
                fam[name]["status"] = "done"
                fam[name]["trials"] = total
                fam[name]["best_train"] = best
            continue
        m = RE_NOTRIALS.search(l)
        if m and m.group(1) in fam:
            fam[m.group(1)]["status"] = "done"
            continue
        if RE_FINAL.search(l):
            status["phase"] = "final: OOS + Monte Carlo"
            current = ("final", None)
            continue
        m = RE_OOS.search(l)
        if m:
            status["finalists"].append({
                "family": m.group(1), "trades": int(m.group(2)),
                "win_rate": float(m.group(3)), "pf": m.group(4),
                "dd": m.group(5), "score": m.group(6), "mc": None, "targets_met": None,
            })
            continue
        m = RE_COMPLETE.search(l)
        if m:
            status["running"] = False
            status["phase"] = "complete"
            status["verdict"] = m.group(2)
            status["ran_h"] = float(m.group(1))

    status["families"] = fam
    status["refinement"] = refinement

    # Enrich finalists from structured results if available
    results = _load_json(RESULTS)
    if results and results.get("finalists"):
        rich = []
        for r in results["finalists"]:
            m = r.get("oos_metrics", {})
            mc = r.get("oos_mc", {})
            boot = mc.get("bootstrap", {}) if mc.get("valid") else {}
            rich.append({
                "family": r["family"], "trades": m.get("trade_count", 0),
                "win_rate": m.get("win_rate_%", 0), "pf": str(m.get("profit_factor")),
                "dd": str(m.get("max_dd_pts")), "score": str(r.get("oos_score")),
                "val_score": r.get("val_score"),
                "mc": {
                    "wr_p5": boot.get("win_rate_%", {}).get("p5"),
                    "pf_p5": boot.get("profit_factor", {}).get("p5"),
                    "dd_p95": boot.get("max_dd_pts", {}).get("p95"),
                } if boot else None,
                "mc_passed": r.get("mc_gate", {}).get("passed"),
                "targets_met": r.get("targets_met"),
            })
        status["finalists"] = rich

    # Checkpoint adds VAL candidates per family
    ckpt = _load_json(CHECKPOINT)
    if ckpt:
        for name, fdata in ckpt.get("families", {}).items():
            if name in fam and fdata.get("top_val"):
                top = fdata["top_val"][0]
                fam[name]["val_score"] = top.get("val_score")
                fam[name]["val_metrics"] = top.get("val_metrics")

    return status


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/api/status"):
            self._send(200, json.dumps(build_status(), default=str), "application/json")
        elif self.path in ("/", "/campaign.html"):
            self._send(200, _read(HTML) or "campaign.html missing", "text/html")
        else:
            self._send(404, "not found", "text/plain")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8770)
    args = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Campaign monitor → http://localhost:{args.port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
