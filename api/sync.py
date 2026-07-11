"""XAUUSD data sync — download real Dukascopy bars and merge into data/.

Shells out to `npx dukascopy-node` (needs Node.js + internet), then reuses
data/convert_dukascopy.convert() to merge into data/XAUUSD_{M15,H1,H4}.csv.

First sync (no marker file) is FULL: the existing CSVs are assumed synthetic,
each is deleted right before its converted replacement is written, and full
history from FULL_START is downloaded. Once data/.sync_meta.json exists,
syncs are incremental from each timeframe's last bar (minus overlap; the
convert merge dedups). `mode="full"` forces a wipe re-download.

Runs on a daemon thread; poll get_status(). Single-flight: a second
start_sync() while running returns False.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

import config
from api.logger import log_event

FULL_START = "2020-01-01"
INCREMENTAL_OVERLAP_DAYS = 2
SUBPROCESS_TIMEOUT = 14400  # 4h per timeframe — dukascopy's datafeed host can take
                             # minutes per artifact on this network; the on-disk
                             # cache (--cache-path) means a killed/failed run still
                             # banks progress for the next attempt.
CACHE_DIR = config.DATA_DIR / ".dukascopy_cache"

# Dukascopy CLI timeframe name → our timeframe key
DUKA_TFS = {"m15": "M15", "h1": "H1", "h4": "H4"}

_lock = threading.Lock()
_state: dict = {
    "status": "idle",       # idle | running | done | error
    "mode": None,           # "full" | "incremental"
    "step": None,
    "started_at": None,
    "finished_at": None,
    "error": None,
}


def _marker_path() -> Path:
    return config.DATA_DIR / ".sync_meta.json"


def read_marker() -> Optional[dict]:
    p = _marker_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return None


def resolve_mode(requested: str, marker: Optional[dict]) -> str:
    """"auto" → full when no successful sync has ever run, else incremental."""
    if requested == "full":
        return "full"
    return "incremental" if marker else "full"


def compute_from_date(tf: str, mode: str, today: Optional[date] = None) -> str:
    """Start date for the dukascopy download of one timeframe."""
    if mode == "full":
        return FULL_START
    csv_path = config.DATA_DIR / config.TF_TO_FILE[tf]
    if not csv_path.exists():
        return FULL_START
    df = pd.read_csv(csv_path, index_col="time", parse_dates=True)
    if df.empty:
        return FULL_START
    last_bar = df.index.max().date()
    return str(last_bar - timedelta(days=INCREMENTAL_OVERLAP_DAYS))


def get_status() -> dict:
    with _lock:
        state = dict(_state)
    marker = read_marker()
    state["last_synced"] = marker.get("last_synced") if marker else None
    return state


def _set(**kwargs) -> None:
    with _lock:
        _state.update(kwargs)


def start_sync(mode: str = "auto") -> Optional[str]:
    """Kick off a sync thread. Returns the resolved mode, or None if a sync
    is already running."""
    resolved = resolve_mode(mode, read_marker())
    with _lock:
        if _state["status"] == "running":
            return None
        _state.update(status="running", mode=resolved, step="starting",
                      started_at=datetime.now(timezone.utc).isoformat(),
                      finished_at=None, error=None)
    threading.Thread(target=_worker, args=(resolved,), daemon=True).start()
    return resolved


def _fail(message: str) -> None:
    _set(status="error", error=message,
         finished_at=datetime.now(timezone.utc).isoformat())
    log_event("data_sync_failed", error=message)


def _worker(mode: str) -> None:
    from data.convert_dukascopy import convert

    if shutil.which("npx") is None:
        _fail("npx not found — install Node.js to sync Dukascopy data")
        return

    # dukascopy-node's -to is exclusive, and today's file isn't published
    # until the session rolls over — requesting through "today" (exclusive)
    # gets everything through yesterday without hitting a guaranteed-missing
    # file that would exhaust retries and fail the whole run every time.
    to_date = str(date.today())
    tf_summary: dict = {}

    for duka_tf, tf in DUKA_TFS.items():
        from_date = compute_from_date(tf, mode)
        _set(step=f"downloading {duka_tf} ({from_date} → {to_date})")
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd = ["npx", "--yes", "dukascopy-node", "-i", "xauusd",
                   "-from", from_date, "-to", to_date,
                   "-t", duka_tf, "-f", "csv", "-dir", tmpdir,
                   # dukascopy's datafeed host is slow (~10-15s/artifact) and
                   # flaky under this network — retries + a persistent cache
                   # so a later attempt resumes instead of refetching
                   # everything from scratch.
                   "--retries", "8", "--retry-pause", "3000",
                   "--retry-on-empty",
                   "--cache", "--cache-path", str(CACHE_DIR)]
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True,
                                      timeout=SUBPROCESS_TIMEOUT)
            except subprocess.TimeoutExpired:
                _fail(f"{duka_tf} download timed out after {SUBPROCESS_TIMEOUT}s")
                return
            if proc.returncode != 0:
                tail = (proc.stderr or proc.stdout or "").strip()[-500:]
                _fail(f"{duka_tf} download failed: {tail}")
                return

            matches = sorted(Path(tmpdir).glob(f"xauusd-{duka_tf}-*.csv"))
            if not matches:
                # A short incremental window over a weekend can legitimately
                # produce nothing — skip this TF, keep going.
                tf_summary[tf] = {"downloaded": 0}
                continue

            _set(step=f"converting {duka_tf}")
            out_path = config.DATA_DIR / config.TF_TO_FILE[tf]
            if mode == "full" and out_path.exists():
                # Wipe per-TF only after its own download succeeded, so a
                # failed download never leaves a timeframe empty.
                out_path.unlink()
            try:
                convert(matches, config.TF_TO_FILE[tf])
            except Exception as e:  # malformed CSV etc.
                _fail(f"{duka_tf} conversion failed: {e}")
                return
            df = pd.read_csv(out_path, index_col="time", parse_dates=True)
            tf_summary[tf] = {"bars": len(df), "end": str(df.index.max().date())}

    now = datetime.now(timezone.utc).isoformat()
    _marker_path().write_text(json.dumps(
        {"last_synced": now, "mode": mode, "timeframes": tf_summary}, indent=2))
    _set(status="done", step="done", finished_at=now)
    log_event("data_sync_completed", mode=mode, timeframes=tf_summary)
