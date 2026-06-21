"""Structured activity logger — appends NDJSON lines to logs/activity.ndjson."""
from __future__ import annotations

import json
import math
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import LOGS_DIR

_LOG_FILE = LOGS_DIR / "activity.ndjson"
_lock = threading.Lock()


def _sanitize(val: Any) -> Any:
    """Recursively replace inf/nan floats with None so output is strict JSON."""
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None
    if isinstance(val, dict):
        return {k: _sanitize(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_sanitize(v) for v in val]
    return val


def log_event(event_type: str, **kwargs: Any) -> None:
    record = _sanitize({
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": event_type,
        **kwargs,
    })
    LOGS_DIR.mkdir(exist_ok=True)
    with _lock:
        with open(_LOG_FILE, "a") as f:
            f.write(json.dumps(record, default=str) + "\n")


def read_logs(limit: int = 200, event_type: str | None = None) -> list[dict]:
    """Read the last `limit` log entries, newest first."""
    if not _LOG_FILE.exists():
        return []
    lines = _LOG_FILE.read_text().strip().splitlines()
    records = []
    for line in reversed(lines):
        try:
            r = json.loads(line)
            r = _sanitize(r)  # strip inf/nan from legacy lines
        except json.JSONDecodeError:
            continue
        if event_type is None or r.get("type") == event_type:
            records.append(r)
        if len(records) >= limit:
            break
    return records
