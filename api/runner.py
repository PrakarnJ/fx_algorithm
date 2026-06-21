"""BacktestRunner: orchestrates batch algo × symbol backtests."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from itertools import product
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from algorithms.registry import get_algo
from api.logger import log_event
from api.schemas import BacktestJobStatus, ComboResult, MetricsResult, TradeResult
from backtest.engine import run_backtest_fast
from backtest.metrics import compute_metrics, compute_r_metrics
from config import SHARED
from data_pipeline.capabilities import check_capability
from data_pipeline.downloader import load_symbol_data
from stocks.loader import get_symbol_spread

# In-memory data cache keyed by (symbol, sorted_tfs_tuple) — CSVs don't change at runtime
_data_cache: Dict[tuple, Dict[str, pd.DataFrame]] = {}


def _serialize_trade(t) -> TradeResult:
    return TradeResult(
        entry_time=str(t.entry_time),
        exit_time=str(t.exit_time) if t.exit_time else None,
        direction=t.direction,
        entry_price=t.entry_price,
        exit_price=t.exit_price,
        sl=t.sl,
        tp=t.tp,
        profit_pts=t.profit_pts,
    )


def _build_metrics(trades) -> Optional[MetricsResult]:
    if not trades:
        return None
    m = compute_metrics(trades)
    r = compute_r_metrics(trades)
    if m.get("trade_count", 0) == 0:
        return None
    return MetricsResult(
        trade_count=m["trade_count"],
        win_rate_pct=m["win_rate_%"],
        profit_factor=m.get("profit_factor"),
        expectancy_pts=m["expectancy_pts"],
        expectancy_R=r.get("expectancy_R"),
        avg_win_pts=m["avg_win_pts"],
        avg_loss_pts=m["avg_loss_pts"],
        max_dd_pts=m["max_dd_pts"],
        max_dd_R=r.get("max_dd_R"),
        total_profit_pts=m["total_profit_pts"],
        total_R=r.get("total_R"),
        sharpe=m["sharpe"],
    )


def _load_cached(symbol: str, required_tfs: List[str]) -> Dict[str, pd.DataFrame]:
    key = (symbol, tuple(sorted(required_tfs)))
    if key not in _data_cache:
        _data_cache[key] = load_symbol_data(symbol, required_tfs)
    return {k: v.copy() for k, v in _data_cache[key].items()}


def _run_combo_sync(
    algo_name: str,
    symbol: str,
    spread_overrides: Optional[Dict[str, int]],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> ComboResult:
    combo_id = f"{algo_name}_{symbol}_{uuid.uuid4().hex[:8]}"
    run_at = datetime.now(timezone.utc).isoformat()
    manifest = get_algo(algo_name)
    if manifest is None:
        return ComboResult(id=combo_id, algo=algo_name, symbol=symbol,
                           exec_tf="?", metrics=None, trades=[], run_at=run_at,
                           error=f"Unknown algorithm: {algo_name}")

    can_run, reason = check_capability(symbol, manifest.required_tfs)
    if not can_run:
        log_event("backtest_combo_skip", algo=algo_name, symbol=symbol, reason=reason)
        return ComboResult(id=combo_id, algo=algo_name, symbol=symbol,
                           exec_tf=manifest.exec_tf, metrics=None, trades=[],
                           run_at=run_at, error=reason)
    try:
        dfs = _load_cached(symbol, manifest.required_tfs)
        if start_date or end_date:
            for k in dfs:
                if start_date:
                    dfs[k] = dfs[k][dfs[k].index >= start_date]
                if end_date:
                    dfs[k] = dfs[k][dfs[k].index <= end_date]
        spread = (spread_overrides or {}).get(symbol, get_symbol_spread(symbol))
        algo = manifest.strategy_class(manifest.default_params, SHARED)
        if manifest.needs_fit:
            fit_dfs = {k: v.iloc[: int(len(v) * 0.7)] for k, v in dfs.items()}
            algo.fit(fit_dfs)
        trades = run_backtest_fast(algo, SHARED, dfs,
                                   spread_points=spread, exec_tf=manifest.exec_tf)
        metrics = _build_metrics(trades)
        serialized_trades = [_serialize_trade(t) for t in trades]
        log_event("backtest_combo_done", algo=algo_name, symbol=symbol,
                  trade_count=len(trades),
                  pf=metrics.profit_factor if metrics else None)
        return ComboResult(id=combo_id, algo=algo_name, symbol=symbol,
                           exec_tf=manifest.exec_tf, metrics=metrics,
                           trades=serialized_trades, run_at=run_at)
    except Exception as e:
        log_event("backtest_combo_error", algo=algo_name, symbol=symbol, error=str(e))
        return ComboResult(id=combo_id, algo=algo_name, symbol=symbol,
                           exec_tf=manifest.exec_tf, metrics=None, trades=[],
                           run_at=run_at, error=str(e))


# In-memory job store (sufficient for local single-user use)
_jobs: Dict[str, BacktestJobStatus] = {}
_job_results: Dict[str, List[ComboResult]] = {}


def get_job(job_id: str) -> Optional[BacktestJobStatus]:
    return _jobs.get(job_id)


def get_all_results() -> List[ComboResult]:
    all_results = []
    for results in _job_results.values():
        all_results.extend(results)
    all_results.sort(key=lambda r: r.run_at, reverse=True)
    return all_results


async def run_backtest_job(
    job_id: str,
    algo_names: List[str],
    symbols: List[str],
    spread_overrides: Optional[Dict[str, int]],
    ws_broadcast: Optional[Callable] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> None:
    combos = list(product(algo_names, symbols))
    total = len(combos)
    _jobs[job_id] = BacktestJobStatus(job_id=job_id, total=total, done=0,
                                       status="running", results=[])
    _job_results[job_id] = []
    log_event("backtest_start", job_id=job_id, total=total,
              algos=algo_names, symbols=symbols)

    for algo_name, symbol in combos:
        result = await asyncio.to_thread(
            _run_combo_sync, algo_name, symbol, spread_overrides, start_date, end_date
        )
        _job_results[job_id].append(result)
        _jobs[job_id].done += 1
        _jobs[job_id].results.append(result)

        if ws_broadcast:
            await ws_broadcast({
                "type": "progress",
                "job_id": job_id,
                "done": _jobs[job_id].done,
                "total": total,
                "result": result.model_dump(),
            })

    _jobs[job_id].status = "complete"
    log_event("backtest_done", job_id=job_id, total=total)
    if ws_broadcast:
        await ws_broadcast({"type": "done", "job_id": job_id})
