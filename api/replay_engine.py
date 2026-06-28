"""ReplaySession: pre-computes all frames and streams them over WebSocket."""
from __future__ import annotations

import asyncio
import math
import time
import uuid
from datetime import timedelta
from typing import Dict, List, Optional

import pandas as pd

from algorithms.registry import get_algo
from api.logger import log_event
from backtest.engine import ReplayFrame, replay_iter
from config import SHARED
from data_pipeline.capabilities import check_capability
from data_pipeline.downloader import load_symbol_data

SESSION_TTL_SECONDS = 3600  # sessions older than 1 hour are purged on next create


def _sanitize_snapshot(snap: dict) -> dict:
    """Strip NaN/Inf floats — Python json.dumps emits them as bare NaN/Infinity,
    which is invalid JSON and makes the browser's JSON.parse throw silently."""
    return {
        k: v for k, v in snap.items()
        if not (isinstance(v, float) and not math.isfinite(v))
    }


def _serialize_signal(sig) -> Optional[dict]:
    if sig is None:
        return None
    return {
        "direction": sig.direction,
        "entry_price": sig.entry_price,
        "sl": sig.sl,
        "tp": sig.tp,
        "atr": sig.atr,
    }


def _serialize_trade(t) -> Optional[dict]:
    if t is None:
        return None
    return {
        "entry_time": str(t.entry_time),
        "exit_time": str(t.exit_time) if t.exit_time else None,
        "direction": t.direction,
        "entry_price": t.entry_price,
        "sl": t.sl,
        "tp": t.tp,
        "profit_pips": t.profit_pts,
        "open_bars": t.open_bars,
        "outcome": "WIN" if (t.profit_pts or 0) > 0 else "LOSS",
    }


def _serialize_frame(frame: ReplayFrame, total_bars: int) -> dict:
    return {
        "type": "frame",
        "bar_index": frame.bar_index,
        "bar_time": str(frame.bar_time),
        "bar": frame.bar,
        "signal": _serialize_signal(frame.signal),
        "open_trade": _serialize_trade(frame.open_trade_before),
        "trade_closed": _serialize_trade(frame.trade_closed),
        "indicator_snapshot": _sanitize_snapshot(frame.indicator_snapshot),
        "total_bars": total_bars,
    }


class ReplaySession:
    def __init__(self, session_id: str, algo_name: str, symbol: str,
                 start_date: Optional[str] = None, end_date: Optional[str] = None):
        self.session_id = session_id
        self.algo_name = algo_name
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.exec_tf: str = "H1"
        self._frames: List[ReplayFrame] = []
        self._ready = False
        self._error: Optional[str] = None
        self.created_at: float = time.time()

    def build_sync(self, max_bars: int = 2000) -> None:
        """
        Run replay_iter and cache frames. When date range given, uses that window
        (+ 250-bar warmup prepended). Otherwise falls back to last max_bars bars.
        """
        manifest = get_algo(self.algo_name)
        if manifest is None:
            self._error = f"Unknown algorithm: {self.algo_name}"
            return

        can_run, reason = check_capability(self.symbol, manifest.required_tfs)
        if not can_run:
            self._error = reason
            return

        try:
            dfs = load_symbol_data(self.symbol, manifest.required_tfs)
            self.exec_tf = manifest.exec_tf

            # Extra H4 history needed so Daily EMA 89 warms up inside _build_slice.
            # 650 H4 bars ≈ 108 trading days; keep 120 calendar days before cutoff.
            H4_EXTRA_DAYS = 120

            if self.start_date or self.end_date:
                # Date-range mode: slice to requested window, prepend 250-bar warmup
                exec_df = dfs[manifest.exec_tf]
                mask = pd.Series(True, index=exec_df.index)
                if self.start_date:
                    mask &= exec_df.index >= self.start_date
                if self.end_date:
                    mask &= exec_df.index <= self.end_date
                window_start_pos = exec_df.index.get_loc(exec_df[mask].index[0]) if mask.any() else 0
                warmup_start_pos = max(0, window_start_pos - 250)
                cutoff_time = exec_df.index[warmup_start_pos]
                h4_cutoff = cutoff_time - timedelta(days=H4_EXTRA_DAYS)
                dfs = {
                    k: (v[v.index >= h4_cutoff] if k == 'H4' else v[v.index >= cutoff_time])
                    for k, v in dfs.items()
                }
                if self.end_date:
                    dfs = {k: v[v.index <= self.end_date] for k, v in dfs.items()}
            else:
                # Default mode: last max_bars bars with 250-bar warmup
                exec_len = len(dfs[manifest.exec_tf])
                replay_bars = min(max_bars, exec_len - 250)  # leave at least 250 warmup
                keep_exec = replay_bars + 250
                if keep_exec < exec_len:
                    cutoff_time = dfs[manifest.exec_tf].index[-keep_exec]
                    h4_cutoff = cutoff_time - timedelta(days=H4_EXTRA_DAYS)
                    dfs = {
                        k: (v[v.index >= h4_cutoff] if k == 'H4' else v[v.index >= cutoff_time])
                        for k, v in dfs.items()
                    }

            algo = manifest.strategy_class(manifest.default_params, SHARED)
            if manifest.needs_fit:
                fit_dfs = {k: v.iloc[: int(len(v) * 0.7)] for k, v in dfs.items()}
                algo.fit(fit_dfs)
            self._frames = list(replay_iter(algo, SHARED, dfs, exec_tf=manifest.exec_tf))
            self._ready = True
            log_event("replay_session_built", session_id=self.session_id,
                      algo=self.algo_name, symbol=self.symbol,
                      total_bars=len(self._frames))
        except Exception as e:
            self._error = str(e)
            log_event("replay_session_error", session_id=self.session_id, error=str(e))

    @property
    def total_bars(self) -> int:
        return len(self._frames)

    async def stream(self, websocket, action_queue: asyncio.Queue) -> None:
        """Stream frames over WebSocket, responding to play/pause/step/seek actions."""
        if self._error:
            await websocket.send_json({"type": "error", "message": self._error})
            return
        if not self._ready:
            await websocket.send_json({"type": "error", "message": "Session not ready"})
            return

        total = len(self._frames)
        current_idx = 0
        is_playing = False
        speed = 1.0

        log_event("replay_session_start", session_id=self.session_id,
                  algo=self.algo_name, symbol=self.symbol)

        while True:
            # Drain all pending actions from the queue
            try:
                while True:
                    action = action_queue.get_nowait()
                    act = action.get("action", "")
                    if act == "play":
                        is_playing = True
                        speed = max(0.1, min(200.0, float(action.get("speed", speed))))
                    elif act == "pause":
                        is_playing = False
                    elif act == "step":
                        if current_idx < total:
                            frame = self._frames[current_idx]
                            try:
                                await websocket.send_json(_serialize_frame(frame, total))
                            except (RuntimeError, Exception):
                                return
                            current_idx += 1
                    elif act == "step_back":
                        current_idx = max(0, current_idx - 1)
                        frame = self._frames[current_idx]
                        try:
                            await websocket.send_json(_serialize_frame(frame, total))
                        except (RuntimeError, Exception):
                            return
                    elif act == "seek":
                        target = int(action.get("bar_index", 0))
                        current_idx = max(0, min(target, total - 1))
                        frame = self._frames[current_idx]
                        try:
                            await websocket.send_json(_serialize_frame(frame, total))
                        except (RuntimeError, Exception):
                            return
                    elif act == "speed":
                        speed = max(0.1, min(200.0, float(action.get("speed", speed))))
            except asyncio.QueueEmpty:
                pass

            if is_playing:
                if current_idx >= total:
                    try:
                        await websocket.send_json({"type": "done"})
                    except (RuntimeError, Exception):
                        return
                    is_playing = False
                    log_event("replay_session_end", session_id=self.session_id)
                    continue
                frame = self._frames[current_idx]
                try:
                    await websocket.send_json(_serialize_frame(frame, total))
                except (RuntimeError, Exception):
                    return
                current_idx += 1
                await asyncio.sleep(1.0 / speed)
            else:
                # Event-driven wait: block until action arrives (max 1 s) instead of
                # busy-polling every 50 ms — drops CPU from ~20 wakeups/s to ~1.
                try:
                    action = await asyncio.wait_for(action_queue.get(), timeout=1.0)
                    await action_queue.put(action)  # return to queue for drain loop
                except asyncio.TimeoutError:
                    pass


# In-memory session store
_sessions: Dict[str, ReplaySession] = {}


def _cleanup_expired_sessions() -> None:
    now = time.time()
    expired = [sid for sid, s in list(_sessions.items())
               if (now - s.created_at) > SESSION_TTL_SECONDS]
    for sid in expired:
        del _sessions[sid]


def get_session(session_id: str) -> Optional[ReplaySession]:
    return _sessions.get(session_id)


def list_sessions() -> list[str]:
    return list(_sessions.keys())


async def create_session(
    algo_name: str,
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> ReplaySession:
    _cleanup_expired_sessions()
    session_id = str(uuid.uuid4())
    session = ReplaySession(session_id, algo_name, symbol, start_date, end_date)
    _sessions[session_id] = session
    # Build in thread pool (CPU-bound work, avoids blocking event loop)
    await asyncio.to_thread(session.build_sync)
    return session


def delete_session(session_id: str) -> None:
    _sessions.pop(session_id, None)
