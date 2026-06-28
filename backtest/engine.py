"""
Bar-by-bar backtesting engine — fast path.

run_backtest_fast():
  - Calls strategy.generate_signals() once (vectorized, O(n) indicator cost).
  - Supports partial TP (close 50% at partial_tp price, move SL to entry).
  - Supports time-stop (close after N H1 bars).
  - SL checked before TP on same bar (conservative fill).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dataclasses import dataclass, field
from typing import Generator, Optional, List
import pandas as pd
import numpy as np

from config import SYMBOL, SharedParams
from trade_manager import update_sl

DATA_DIR = Path(__file__).parent.parent / "data"
SPREAD_POINTS = 20


@dataclass
class Trade:
    entry_time: pd.Timestamp
    direction: str
    entry_price: float
    sl: float
    tp: float
    atr: float
    partial_tp: Optional[float] = None        # None = disabled
    time_stop_hours: int = 0                  # 0 = disabled
    full_close_at_partial: bool = False       # scalp mode
    # runtime state
    partial_done: bool = False
    partial_profit: float = 0.0
    open_bars: int = 0
    exit_time: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    profit_pts: Optional[float] = None
    # captured once at entry — never mutated (sl trails, initial_sl does not)
    initial_sl: float = 0.0
    exit_reason: str = ""   # "sl" | "trail" | "tp" | "time" | "eod"


def load_data(symbol: str = SYMBOL) -> dict:
    dfs = {}
    for tf in ("M15", "H1", "H4"):
        path = DATA_DIR / f"{symbol}_{tf}.csv"
        df = pd.read_csv(path, index_col="time", parse_dates=True)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        dfs[tf] = df
    return dfs


def run_backtest_fast(
    strategy,
    shared: SharedParams,
    dfs: dict,
    spread_points: int = SPREAD_POINTS,
    exec_tf: str = "H1",
) -> List[Trade]:
    """exec_tf selects the bar series trades execute on ("H1" or "M15").
    M15 gives 4x finer fill granularity for small-TP scalp strategies."""
    bars = dfs[exec_tf]
    bars_per_hour = 4 if exec_tf == "M15" else 1
    spread = spread_points * 0.01

    signal_df = strategy.generate_signals(dfs)
    if signal_df is None or len(signal_df) == 0:
        return []

    # Align signal times to nearest exec bar at-or-after
    h1_index = bars.index
    sig_lookup: dict = {}
    for sig_time in signal_df.index:
        pos = h1_index.searchsorted(sig_time)
        if pos >= len(h1_index):
            continue
        h1_time = h1_index[pos]
        if h1_time not in sig_lookup:
            sig_lookup[h1_time] = signal_df.loc[sig_time]

    warmup_time   = h1_index[250 * bars_per_hour]
    trades: List[Trade] = []
    open_trade: Optional[Trade] = None
    consec_losses = 0
    pause_until: Optional[pd.Timestamp] = None
    # Per-strategy trail override (e.g. TrendBreakoutParams, TrendFollowingParams)
    _strat_be   = getattr(strategy.p, "breakeven_atr_mult", None)
    _strat_trail = getattr(strategy.p, "trail_atr_mult", None)

    for i in range(len(bars)):
        bar_time = h1_index[i]
        if bar_time < warmup_time:
            continue
        bar = bars.iloc[i]
        high, low, close = bar["high"], bar["low"], bar["close"]

        # ── Manage open trade ─────────────────────────────────────
        if open_trade is not None:
            open_trade.open_bars += 1

            # Update SL (stepped or ATR trail depending on strategy)
            open_trade.sl = update_sl(
                open_trade.direction, open_trade.entry_price,
                open_trade.sl, open_trade.atr, close, shared,
                partial_done=open_trade.partial_done,
                breakeven_mult=_strat_be,
                trail_mult=_strat_trail,
                tp=open_trade.tp if getattr(strategy.p, "use_stepped_sl", False) else None,
            )

            # Partial / full-close at partial TP level
            if not open_trade.partial_done and open_trade.partial_tp is not None:
                hit_partial = (
                    (open_trade.direction == "buy"  and high >= open_trade.partial_tp) or
                    (open_trade.direction == "sell" and low  <= open_trade.partial_tp)
                )
                if hit_partial:
                    if open_trade.full_close_at_partial:
                        # Scalp mode: close 100% here, treat like TP hit
                        _close_trade(open_trade, open_trade.partial_tp, bar_time, trades,
                                     force_full=True, shared=shared, exit_reason="tp")
                        consec_losses = 0
                        open_trade = None
                        continue
                    else:
                        if open_trade.direction == "buy":
                            open_trade.partial_profit = 0.5 * (open_trade.partial_tp - open_trade.entry_price)
                        else:
                            open_trade.partial_profit = 0.5 * (open_trade.entry_price - open_trade.partial_tp)
                        open_trade.partial_done = True
                        open_trade.sl = open_trade.entry_price  # move to break-even

            # Time-stop: close at bar close after N hours (open_bars counts exec bars)
            if open_trade.time_stop_hours > 0 and open_trade.open_bars >= open_trade.time_stop_hours * bars_per_hour:
                _close_trade(open_trade, close, bar_time, trades, shared=shared, exit_reason="time")
                consec_losses = consec_losses + 1 if open_trade.profit_pts < 0 else 0
                open_trade = None
                continue

            # SL hit (check before TP — conservative)
            hit_sl = (
                (open_trade.direction == "buy"  and low  <= open_trade.sl) or
                (open_trade.direction == "sell" and high >= open_trade.sl)
            )
            hit_tp = (
                (open_trade.direction == "buy"  and high >= open_trade.tp) or
                (open_trade.direction == "sell" and low  <= open_trade.tp)
            )

            if hit_sl:
                _close_trade(open_trade, open_trade.sl, bar_time, trades, shared=shared, is_sl_hit=True)
                consec_losses = consec_losses + 1 if open_trade.profit_pts < 0 else 0
                open_trade = None
            elif hit_tp:
                _close_trade(open_trade, open_trade.tp, bar_time, trades, shared=shared)
                consec_losses = 0
                open_trade = None
            continue

        # ── Drawdown guard ────────────────────────────────────────
        if pause_until is not None and bar_time < pause_until:
            continue
        if consec_losses >= shared.max_consec_losses:
            pause_until = bar_time + pd.Timedelta(hours=shared.consec_loss_pause_hours)
            consec_losses = 0
            continue

        # ── Enter new trade ───────────────────────────────────────
        sig = sig_lookup.get(bar_time)
        if sig is None:
            continue

        entry = (
            float(sig["entry"]) + spread
            if sig["direction"] == "buy"
            else float(sig["entry"]) - spread
        )
        partial_tp_raw = sig.get("partial_tp", float("nan"))
        partial_tp = None if (partial_tp_raw is None or (isinstance(partial_tp_raw, float) and np.isnan(partial_tp_raw))) else float(partial_tp_raw)
        time_stop = int(getattr(strategy.p, "time_stop_hours", 0))

        initial_sl = float(sig["sl"])
        open_trade = Trade(
            entry_time=bar_time,
            direction=sig["direction"],
            entry_price=entry,
            sl=initial_sl,
            tp=float(sig["tp"]),
            atr=float(sig["atr"]),
            partial_tp=partial_tp,
            time_stop_hours=time_stop,
            full_close_at_partial=bool(getattr(strategy.p, "full_close_at_partial", False)),
            initial_sl=initial_sl,
        )

    if open_trade is not None:
        _close_trade(open_trade, bars.iloc[-1]["close"], bars.index[-1], trades,
                     shared=shared, exit_reason="eod")

    return trades


def _close_trade(
    trade: Trade,
    exit_price: float,
    exit_time: pd.Timestamp,
    trades: list,
    force_full: bool = False,
    shared: Optional[SharedParams] = None,
    is_sl_hit: bool = False,
    exit_reason: str = "",
) -> None:
    if is_sl_hit and shared is not None and shared.slippage_pts > 0:
        slip = shared.slippage_pts * 0.01
        exit_price = (exit_price - slip if trade.direction == "buy" else exit_price + slip)

    trade.exit_price = exit_price
    trade.exit_time  = exit_time
    raw = (
        exit_price - trade.entry_price
        if trade.direction == "buy"
        else trade.entry_price - exit_price
    )
    profit = raw if (force_full or not trade.partial_done) else trade.partial_profit + 0.5 * raw

    if shared is not None:
        profit -= shared.commission_pts * 0.01
        nights = max(0, (exit_time - trade.entry_time).days)
        profit -= shared.swap_pts_per_night * 0.01 * nights

    trade.profit_pts = profit
    # Resolve exit reason: "trail" when a stop that trailed past entry captures profit
    if not exit_reason and is_sl_hit:
        exit_reason = "trail" if profit > 0 else "sl"
    trade.exit_reason = exit_reason or "tp"
    trades.append(trade)


# Slow rolling-slice reference implementation (used for correctness checks)
def run_backtest(
    strategy,
    shared: SharedParams,
    dfs: dict,
    spread_points: int = SPREAD_POINTS,
) -> List[Trade]:
    h1 = dfs["H1"]
    spread = spread_points * 0.01
    trades: List[Trade] = []
    open_trade: Optional[Trade] = None
    consec_losses = 0
    pause_until: Optional[pd.Timestamp] = None
    warmup = 250
    _strat_be    = getattr(strategy.p, "breakeven_atr_mult", None)
    _strat_trail = getattr(strategy.p, "trail_atr_mult", None)

    for i in range(warmup, len(h1)):
        bar = h1.iloc[i]
        bar_time = h1.index[i]
        high, low, close = bar["high"], bar["low"], bar["close"]

        if open_trade is not None:
            open_trade.sl = update_sl(
                open_trade.direction, open_trade.entry_price,
                open_trade.sl, open_trade.atr, close, shared,
                breakeven_mult=_strat_be, trail_mult=_strat_trail,
                tp=open_trade.tp if getattr(strategy.p, "use_stepped_sl", False) else None,
            )
            hit_sl = (open_trade.direction == "buy"  and low  <= open_trade.sl) or \
                     (open_trade.direction == "sell" and high >= open_trade.sl)
            hit_tp = (open_trade.direction == "buy"  and high >= open_trade.tp) or \
                     (open_trade.direction == "sell" and low  <= open_trade.tp)
            if hit_sl:
                _close_trade(open_trade, open_trade.sl, bar_time, trades, shared=shared, is_sl_hit=True)
                consec_losses = consec_losses + 1 if open_trade.profit_pts < 0 else 0
                open_trade = None
            elif hit_tp:
                _close_trade(open_trade, open_trade.tp, bar_time, trades, shared=shared)
                consec_losses = 0
                open_trade = None
            continue

        if pause_until is not None and bar_time < pause_until:
            continue
        if consec_losses >= shared.max_consec_losses:
            pause_until = bar_time + pd.Timedelta(hours=shared.consec_loss_pause_hours)
            consec_losses = 0
            continue

        slice_dfs = {
            "M15": dfs["M15"].loc[dfs["M15"].index <= bar_time].iloc[-600:],
            "H1":  h1.iloc[: i + 1].iloc[-500:],
            "H4":  dfs["H4"].loc[dfs["H4"].index <= bar_time].iloc[-300:],
        }
        signal = strategy.get_signal(slice_dfs)
        if signal is None:
            continue

        entry = signal.entry_price + spread if signal.direction == "buy" else signal.entry_price - spread
        open_trade = Trade(
            entry_time=bar_time, direction=signal.direction,
            entry_price=entry, sl=signal.sl, tp=signal.tp, atr=signal.atr,
            initial_sl=signal.sl,
        )

    if open_trade is not None:
        _close_trade(open_trade, h1.iloc[-1]["close"], h1.index[-1], trades,
                     shared=shared, exit_reason="eod")
    return trades


# ── Replay engine (bar-by-bar generator for the chart player UI) ──────────────

@dataclass
class ReplayFrame:
    bar_index: int
    bar_time: pd.Timestamp
    bar: dict                       # {"open", "high", "low", "close"}
    signal: Optional[object]        # Signal dataclass or None
    open_trade_before: Optional[Trade]  # snapshot of trade state entering this bar
    trade_closed: Optional[Trade]   # trade that closed this bar, or None
    indicator_snapshot: dict        # from strategy.get_indicators()


def replay_iter(
    strategy,
    shared: SharedParams,
    dfs: dict,
    exec_tf: str = "H1",
    spread_points: int = SPREAD_POINTS,
) -> Generator[ReplayFrame, None, None]:
    """
    Generator version of run_backtest (slow rolling path).
    Yields one ReplayFrame per bar starting after warmup.
    Caller (ReplaySession) collects frames into a list for O(1) seek.
    """
    exec_bars = dfs[exec_tf]
    spread = spread_points * 0.01
    warmup = 250
    open_trade: Optional[Trade] = None
    consec_losses = 0
    pause_until: Optional[pd.Timestamp] = None

    # Window sizes for rolling slice — enough for all indicator lookbacks.
    # H4=650 so strategies that resample to Daily can compute EMA 89
    # (650 H4 bars ≈ 108 trading days >> 89 bars needed).
    _slice_sizes = {"M15": 600, "M30": 400, "H1": 500, "H4": 650, "D1": 150,
                    "W1": 100, "MN": 60, "M5": 1000, "M1": 2000}

    def _build_slice(bar_time: pd.Timestamp) -> dict:
        slices = {}
        for key, df in dfs.items():
            n = _slice_sizes.get(key, 400)
            slices[key] = df.loc[df.index <= bar_time].iloc[-n:]
        return slices

    total = len(exec_bars) - warmup

    for i in range(warmup, len(exec_bars)):
        bar_time = exec_bars.index[i]
        bar = exec_bars.iloc[i]
        high, low, close = bar["high"], bar["low"], bar["close"]
        bar_dict = {"open": float(bar["open"]), "high": float(high),
                    "low": float(low), "close": float(close)}

        # Snapshot of trade entering this bar (before management)
        trade_before = None
        if open_trade is not None:
            from copy import copy
            trade_before = copy(open_trade)

        trade_closed: Optional[Trade] = None
        signal = None

        if open_trade is not None:
            open_trade.open_bars += 1
            open_trade.sl = update_sl(
                open_trade.direction, open_trade.entry_price,
                open_trade.sl, open_trade.atr, close, shared,
                breakeven_mult=getattr(strategy.p, "breakeven_atr_mult", None),
                trail_mult=getattr(strategy.p, "trail_atr_mult", None),
                tp=open_trade.tp if getattr(strategy.p, "use_stepped_sl", False) else None,
            )
            hit_sl = (open_trade.direction == "buy"  and low  <= open_trade.sl) or \
                     (open_trade.direction == "sell" and high >= open_trade.sl)
            hit_tp = (open_trade.direction == "buy"  and high >= open_trade.tp) or \
                     (open_trade.direction == "sell" and low  <= open_trade.tp)
            if hit_sl:
                _close_trade(open_trade, open_trade.sl, bar_time, [], shared=shared, is_sl_hit=True)
                consec_losses = consec_losses + 1 if open_trade.profit_pts < 0 else 0
                trade_closed = open_trade
                open_trade = None
            elif hit_tp:
                _close_trade(open_trade, open_trade.tp, bar_time, [], shared=shared)
                consec_losses = 0
                trade_closed = open_trade
                open_trade = None
        else:
            if not (pause_until is not None and bar_time < pause_until):
                if consec_losses >= shared.max_consec_losses:
                    pause_until = bar_time + pd.Timedelta(hours=shared.consec_loss_pause_hours)
                    consec_losses = 0
                else:
                    slice_dfs = _build_slice(bar_time)
                    signal = strategy.get_signal(slice_dfs)
                    if signal is not None:
                        entry = (signal.entry_price + spread if signal.direction == "buy"
                                 else signal.entry_price - spread)
                        open_trade = Trade(
                            entry_time=bar_time, direction=signal.direction,
                            entry_price=entry, sl=signal.sl, tp=signal.tp, atr=signal.atr,
                            initial_sl=signal.sl,
                        )

        # Indicator snapshot (optional — strategies may override get_indicators)
        try:
            slice_dfs = _build_slice(bar_time)
            indicator_snapshot = strategy.get_indicators(slice_dfs)
        except Exception:
            indicator_snapshot = {}

        yield ReplayFrame(
            bar_index=i - warmup,
            bar_time=bar_time,
            bar=bar_dict,
            signal=signal,
            open_trade_before=trade_before,
            trade_closed=trade_closed,
            indicator_snapshot=indicator_snapshot,
        )

    # Force-close any remaining open trade at last bar
    if open_trade is not None:
        last_close = float(exec_bars.iloc[-1]["close"])
        _close_trade(open_trade, last_close, exec_bars.index[-1], [], shared=shared)
        trade_before = None
        from copy import copy
        trade_before = copy(open_trade)
        yield ReplayFrame(
            bar_index=len(exec_bars) - 1 - warmup,
            bar_time=exec_bars.index[-1],
            bar={"open": last_close, "high": last_close, "low": last_close, "close": last_close},
            signal=None,
            open_trade_before=trade_before,
            trade_closed=open_trade,
            indicator_snapshot={},
        )
