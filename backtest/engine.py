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
from typing import Optional, List
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

    for i in range(len(bars)):
        bar_time = h1_index[i]
        if bar_time < warmup_time:
            continue
        bar = bars.iloc[i]
        high, low, close = bar["high"], bar["low"], bar["close"]

        # ── Manage open trade ─────────────────────────────────────
        if open_trade is not None:
            open_trade.open_bars += 1

            # Update SL (break-even / ATR trail — tighter after partial)
            open_trade.sl = update_sl(
                open_trade.direction, open_trade.entry_price,
                open_trade.sl, open_trade.atr, close, shared,
                partial_done=open_trade.partial_done,
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
                                     force_full=True)
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
                _close_trade(open_trade, close, bar_time, trades)
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
                _close_trade(open_trade, open_trade.sl, bar_time, trades)
                consec_losses = consec_losses + 1 if open_trade.profit_pts < 0 else 0
                open_trade = None
            elif hit_tp:
                _close_trade(open_trade, open_trade.tp, bar_time, trades)
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

        open_trade = Trade(
            entry_time=bar_time,
            direction=sig["direction"],
            entry_price=entry,
            sl=float(sig["sl"]),
            tp=float(sig["tp"]),
            atr=float(sig["atr"]),
            partial_tp=partial_tp,
            time_stop_hours=time_stop,
            full_close_at_partial=bool(getattr(strategy.p, "full_close_at_partial", False)),
        )

    if open_trade is not None:
        _close_trade(open_trade, bars.iloc[-1]["close"], bars.index[-1], trades)

    return trades


def _close_trade(
    trade: Trade,
    exit_price: float,
    exit_time: pd.Timestamp,
    trades: list,
    force_full: bool = False,
) -> None:
    trade.exit_price = exit_price
    trade.exit_time  = exit_time
    raw = (
        exit_price - trade.entry_price
        if trade.direction == "buy"
        else trade.entry_price - exit_price
    )
    if force_full or not trade.partial_done:
        trade.profit_pts = raw
    else:
        # 50% already closed at partial_tp; 50% closing now
        trade.profit_pts = trade.partial_profit + 0.5 * raw
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

    for i in range(warmup, len(h1)):
        bar = h1.iloc[i]
        bar_time = h1.index[i]
        high, low, close = bar["high"], bar["low"], bar["close"]

        if open_trade is not None:
            open_trade.sl = update_sl(
                open_trade.direction, open_trade.entry_price,
                open_trade.sl, open_trade.atr, close, shared,
            )
            hit_sl = (open_trade.direction == "buy"  and low  <= open_trade.sl) or \
                     (open_trade.direction == "sell" and high >= open_trade.sl)
            hit_tp = (open_trade.direction == "buy"  and high >= open_trade.tp) or \
                     (open_trade.direction == "sell" and low  <= open_trade.tp)
            if hit_sl:
                _close_trade(open_trade, open_trade.sl, bar_time, trades)
                consec_losses = consec_losses + 1 if open_trade.profit_pts < 0 else 0
                open_trade = None
            elif hit_tp:
                _close_trade(open_trade, open_trade.tp, bar_time, trades)
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
        )

    if open_trade is not None:
        _close_trade(open_trade, h1.iloc[-1]["close"], h1.index[-1], trades)
    return trades
