"""Pydantic v2 request/response models for the FX Algorithm Platform API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class AlgoInfo(BaseModel):
    name: str
    display_name: str
    required_tfs: List[str]
    exec_tf: str
    needs_fit: bool
    description: str
    indicator_keys: List[str]


class SymbolInfo(BaseModel):
    symbol: str
    name: str
    tick_size: float
    spread_points: int
    yfinance_ticker: str
    available_tfs: List[str]


class DownloadRequest(BaseModel):
    symbols: List[str]
    internal_tfs: List[str]   # e.g. ["H1", "H4", "D1"]


class BacktestRequest(BaseModel):
    algo_names: List[str]
    symbols: List[str]
    spread_overrides: Optional[Dict[str, int]] = None  # symbol → spread_points
    start_date: Optional[str] = None  # "YYYY-MM-DD"
    end_date: Optional[str] = None    # "YYYY-MM-DD"


class MetricsResult(BaseModel):
    trade_count: int
    win_rate_pct: float
    profit_factor: Optional[float]
    expectancy_pts: float
    expectancy_R: Optional[float] = None
    avg_win_pts: float
    avg_loss_pts: float
    max_dd_pts: float
    max_dd_R: Optional[float] = None
    total_profit_pts: float
    total_R: Optional[float] = None
    sharpe: float


class TradeResult(BaseModel):
    entry_time: str
    exit_time: Optional[str]
    direction: str
    entry_price: float
    exit_price: Optional[float]
    sl: float
    tp: float
    profit_pts: Optional[float]


class ComboResult(BaseModel):
    id: str
    algo: str
    symbol: str
    exec_tf: str
    metrics: Optional[MetricsResult]
    trades: List[TradeResult]
    run_at: str
    error: Optional[str] = None


class BacktestJobStatus(BaseModel):
    job_id: str
    total: int
    done: int
    status: str   # "running" | "complete" | "error"
    results: List[ComboResult]


class ReplayStartRequest(BaseModel):
    algo_name: str
    symbol: str
    start_date: Optional[str] = None  # "YYYY-MM-DD"
    end_date: Optional[str] = None    # "YYYY-MM-DD"


class ReplayStartResponse(BaseModel):
    session_id: str
    total_bars: int
    algo_name: str
    symbol: str
    exec_tf: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
