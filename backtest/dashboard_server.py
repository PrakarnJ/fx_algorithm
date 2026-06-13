"""
Unified dashboard + control server for the XAUUSD bot.

One server, one UI (report/index.html), four tabs:
  Overview     — headline KPIs, current strategy/params, equity curve
  Performance  — variant explorer, charts, comparison (from report/data.json)
  Optimize     — trigger re-optimization, watch progress, review proposal, Apply
  Deploy       — ACTIVE_STRATEGY, live params, demo-first deployment status

Read-only data endpoints + control endpoints that wrap the CLI tools:
  GET  /api/overview            current strategy, params, data range, re-opt status
  GET  /api/performance         report/data.json (walk-forward + variants)
  POST /api/reoptimize          launch backtest/reoptimize.py in the background
  GET  /api/reoptimize/status   live progress of a running re-optimization
  GET  /api/proposal            the latest proposed params (old vs new + metrics)
  POST /api/apply               apply the proposal (writes data/regime_params.json)
  GET  /api/campaign            optuna campaign progress (if any)

Run:  python backtest/dashboard_server.py [--port 8765]
"""
import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

REPORT_DIR = ROOT / "report"
RUN_DIR = ROOT / "backtest" / "campaign_runs"
DATA_JSON = REPORT_DIR / "data.json"
STATUS = RUN_DIR / "reoptimize_status.json"
PROPOSAL = RUN_DIR / "reoptimize_proposal.json"
OVERRIDE = ROOT / "data" / "regime_params.json"
REOPT = ROOT / "backtest" / "reoptimize.py"

_reopt_proc = {"p": None}   # handle to a running re-optimization


def _read_json(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def overview():
    # imported lazily so a freshly-applied override is picked up
    import importlib, config
    importlib.reload(config)
    rp = config.REGIME_PARAMS
    data = _read_json(DATA_JSON) or {}
    # headline = the regime_switch walk-forward variant
    headline = None
    for v in data.get("variants", []):
        if "regime" in v["key"]:
            headline = v["windows"].get("walkforward", {}).get("metrics")
            break
    h1 = ROOT / "data" / "XAUUSD_H1.csv"
    data_range = None
    if h1.exists():
        import pandas as pd
        idx = pd.read_csv(h1, usecols=["time"], parse_dates=["time"])["time"]
        data_range = {"start": str(idx.iloc[0].date()), "end": str(idx.iloc[-1].date()),
                      "bars": len(idx)}
    st = _read_json(STATUS)
    return {
        "active_strategy": config.ACTIVE_STRATEGY,
        "params": _params_dict(rp),
        "override_active": OVERRIDE.exists(),
        "headline_metrics": headline,
        "data_range": data_range,
        "reoptimize": {"running": bool(st and st.get("running")),
                       "last": st, "proposal_ready": PROPOSAL.exists()},
        "now": datetime.now(timezone.utc).isoformat(),
    }


def _params_dict(rp):
    from dataclasses import asdict
    return asdict(rp)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, default=str))

    # ── GET ────────────────────────────────────────────────────────────
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/overview":
            return self._json(overview())
        if path == "/api/performance":
            return self._send(200, (DATA_JSON.read_text() if DATA_JSON.exists()
                                     else "{}"))
        if path == "/api/reoptimize/status":
            return self._json(_read_json(STATUS) or {"stage": "idle", "running": False})
        if path == "/api/proposal":
            return self._json(_read_json(PROPOSAL) or {})
        if path == "/api/campaign":
            return self._json(_read_json(RUN_DIR / "checkpoint.json") or {})
        if path in ("/", "/index.html"):
            f = REPORT_DIR / "index.html"
            return self._send(200, f.read_text() if f.exists() else "missing", "text/html")
        # static assets (app.js, style.css)
        asset = REPORT_DIR / path.lstrip("/")
        if asset.exists() and asset.is_file():
            ctype = ("application/javascript" if asset.suffix == ".js"
                     else "text/css" if asset.suffix == ".css" else "text/plain")
            return self._send(200, asset.read_text(), ctype)
        return self._send(404, "not found", "text/plain")

    # ── POST ───────────────────────────────────────────────────────────
    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/reoptimize":
            return self._launch_reoptimize()
        if path == "/api/apply":
            return self._apply()
        return self._send(404, "not found", "text/plain")

    def _launch_reoptimize(self):
        if _reopt_proc["p"] and _reopt_proc["p"].poll() is None:
            return self._json({"ok": False, "error": "already running"}, 409)
        # read optional body {download: bool, trials: int}
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = json.loads(self.rfile.read(length) or "{}") if length else {}
        cmd = [sys.executable, str(REOPT),
               "--trials", str(body.get("trials", 60)),
               "--wf-trials", str(body.get("wf_trials", 20))]
        if not body.get("download", True):
            cmd.append("--no-download")
        log = open(RUN_DIR / "reoptimize.out", "w")
        _reopt_proc["p"] = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=str(ROOT))
        return self._json({"ok": True, "message": "re-optimization started"})

    def _apply(self):
        try:
            out = subprocess.run([sys.executable, str(REOPT), "--apply"],
                                 capture_output=True, text=True, cwd=str(ROOT), timeout=60)
            ok = out.returncode == 0
            return self._json({"ok": ok, "stdout": out.stdout, "stderr": out.stderr},
                              200 if ok else 500)
        except Exception as e:
            return self._json({"ok": False, "error": str(e)}, 500)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Unified dashboard → http://localhost:{args.port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
