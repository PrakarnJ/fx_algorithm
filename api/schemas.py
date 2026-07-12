"""Pydantic v2 request/response models for the XAUUSD Pine Studio API."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


# ── Pine compile / backtest ─────────────────────────────────────────────────

class PineSource(BaseModel):
    source: str


class PineError(BaseModel):
    line: int
    col: int
    message: str


class PineValidateResponse(BaseModel):
    ok: bool
    script_type: Optional[str] = None   # "indicator" | "strategy"
    title: Optional[str] = None
    errors: List[PineError] = []


class TesterSettings(BaseModel):
    """Overrides for strategy() declaration args (TradingView tester model)."""
    initial_capital: Optional[float] = None
    default_qty_type: Optional[str] = None    # "fixed" | "percent_of_equity" | "cash"
    default_qty_value: Optional[float] = None
    commission_type: Optional[str] = None     # "none" | "percent" | "cash_per_contract" | "cash_per_order"
    commission_value: Optional[float] = None


class PineBacktestRequest(BaseModel):
    source: str
    timeframe: str = "H1"               # M15 | H1 | H4
    start_date: Optional[str] = None    # "YYYY-MM-DD"
    end_date: Optional[str] = None      # "YYYY-MM-DD"
    settings: Optional[TesterSettings] = None


class PlotSeries(BaseModel):
    id: str
    title: str
    color: str
    style: str = "line"                 # "line" | "histogram" | "circles"
    overlay: bool = True                # price pane vs separate pane
    # Parallel to bars; None where the series is na
    values: List[Optional[float]]


class ShapeMarker(BaseModel):
    time: int                           # unix seconds
    shape: str                          # "triangleup" | "triangledown" | ...
    location: str                       # "abovebar" | "belowbar" | "absolute"
    color: str
    text: str = ""
    price: Optional[float] = None       # for location == "absolute"


class HLine(BaseModel):
    price: float
    title: str = ""
    color: str = "#787b86"


class TradeRecord(BaseModel):
    entry_time: int                     # unix seconds (fill bar)
    exit_time: Optional[int]
    direction: str                      # "long" | "short"
    entry_price: float
    exit_price: Optional[float]
    qty: float
    profit: Optional[float]             # currency
    profit_pct: Optional[float]
    entry_id: str = ""
    exit_reason: str = ""               # "close" | "stop" | "limit" | "end_of_data"


class TesterMetrics(BaseModel):
    """TradingView Strategy Tester 'Overview' numbers."""
    net_profit: float
    net_profit_pct: float
    gross_profit: float
    gross_loss: float
    profit_factor: Optional[float]
    max_drawdown: float
    max_drawdown_pct: float
    total_trades: int
    percent_profitable: Optional[float]
    avg_trade: Optional[float]
    avg_win: Optional[float]
    avg_loss: Optional[float]
    open_pl: float = 0.0


class ExitLevels(BaseModel):
    """Per-bar active strategy.exit SL/TP prices (null when flat / no rule)."""
    stop: List[Optional[float]] = []
    limit: List[Optional[float]] = []


class PineBacktestResponse(BaseModel):
    ok: bool
    script_type: Optional[str] = None
    title: Optional[str] = None
    errors: List[PineError] = []
    bars: List[Dict[str, Any]] = []     # {time,open,high,low,close}
    plots: List[PlotSeries] = []
    shapes: List[ShapeMarker] = []
    hlines: List[HLine] = []
    trades: List[TradeRecord] = []
    equity: List[Optional[float]] = []  # per-bar equity curve (strategy only)
    exit_levels: Optional[ExitLevels] = None
    metrics: Optional[TesterMetrics] = None


# ── Saved scripts ────────────────────────────────────────────────────────────

class ScriptCreate(BaseModel):
    name: str
    source: str


class ScriptUpdate(BaseModel):
    name: Optional[str] = None
    source: Optional[str] = None


class ScriptMeta(BaseModel):
    id: int
    name: str
    created_at: str
    updated_at: str


class ScriptDetail(ScriptMeta):
    source: str


class ScriptListResponse(BaseModel):
    scripts: List[ScriptMeta]


# ── Ranking ──────────────────────────────────────────────────────────────────

class RankingRequest(BaseModel):
    script_ids: List[int]
    timeframe: str = "M15"              # M15 | H1 | H4
    start_date: Optional[str] = None    # "YYYY-MM-DD"
    end_date: Optional[str] = None      # "YYYY-MM-DD"


class RankingItem(BaseModel):
    script_id: int
    name: str
    ok: bool
    title: Optional[str] = None
    error: Optional[str] = None
    metrics: Optional[TesterMetrics] = None


class RankingResponse(BaseModel):
    ok: bool = True
    timeframe: str
    bars: int
    start: Optional[str] = None
    end: Optional[str] = None
    results: List[RankingItem]
