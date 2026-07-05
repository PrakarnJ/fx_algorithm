"""TradingView-style broker emulator ("Strategy Tester").

Fill model (mirrors TV defaults, no bar magnifier):
  - Orders placed while the script runs on bar i become active on bar i+1.
  - Market orders fill at bar i+1's OPEN.
  - Stop / limit orders (entries and strategy.exit rules) fill intra-bar when
    the bar's range crosses the price.
  - When both a stop and a limit could fill in the same bar, the intra-bar
    price path follows TV's documented assumption: if open is nearer to high,
    the path is open→high→low→close, otherwise open→low→high→close.
  - Single position (pyramiding = 1): a same-direction entry while in a
    position is ignored; an opposite entry reverses.
  - Commission is charged on every fill (entry and exit).

Numbers will be close to, but not identical to, TradingView's tester — TV
applies tick-level heuristics and bar magnification we do not replicate.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from pine.builtins import isna

NAN = float("nan")


@dataclass
class EntryOrder:
    entry_id: str
    direction: str            # "long" | "short"
    qty: Optional[float]      # None → sized at fill from settings
    stop: Optional[float]     # stop entry price
    limit: Optional[float]    # limit entry price


@dataclass
class ExitRule:
    from_entry: str           # "" = applies to any entry
    stop: Optional[float]
    limit: Optional[float]
    loss_ticks: Optional[float]
    profit_ticks: Optional[float]


@dataclass
class Position:
    direction: str
    qty: float
    entry_price: float
    entry_bar: int
    entry_id: str


@dataclass
class ClosedTrade:
    entry_bar: int
    exit_bar: int
    direction: str
    entry_price: float
    exit_price: float
    qty: float
    profit: float             # currency, net of commission
    entry_id: str
    exit_reason: str          # "close" | "stop" | "limit" | "reverse" | "end_of_data"


@dataclass
class TesterSettings:
    initial_capital: float = 100_000.0
    default_qty_type: str = "fixed"       # fixed | percent_of_equity | cash
    default_qty_value: float = 1.0
    commission_type: str = "none"         # none | percent | cash_per_contract | cash_per_order
    commission_value: float = 0.0
    tick_size: float = 0.01
    process_orders_on_close: bool = False  # market orders fill at same-bar close


class Broker:
    """Interleaves with the interpreter: `begin_bar(i)` runs fills for bar i
    *before* the script executes on bar i; strategy.* calls during bar i queue
    orders that activate on bar i+1."""

    def __init__(self, opens: np.ndarray, highs: np.ndarray, lows: np.ndarray,
                 closes: np.ndarray, settings: TesterSettings):
        self.o, self.h, self.l, self.c = opens, highs, lows, closes
        self.s = settings
        self.position: Optional[Position] = None
        self.closed: list[ClosedTrade] = []
        self.realized = 0.0                    # cumulative net P&L (currency)
        self.equity_curve: list[float] = []
        self.size_history: list[float] = []    # position_size as seen by the script each bar

        # Orders queued during the current bar → active next bar
        self._queued_entries: list[EntryOrder] = []
        self._queued_close: Optional[str] = None      # entry_id or "*"
        self._queued_exits: list[ExitRule] = []
        # Active on the current bar (unfilled stop/limit entries persist here)
        self._entries: list[EntryOrder] = []
        self._close: Optional[str] = None
        self._exits: list[ExitRule] = []

    # ── script-facing API (called by the interpreter during bar i) ──────────
    def entry(self, entry_id: str, direction: str, qty=None, stop=None, limit=None):
        # Replace a same-id pending order (TV behavior)
        self._queued_entries = [e for e in self._queued_entries if e.entry_id != entry_id]
        self._queued_entries.append(EntryOrder(
            entry_id=entry_id, direction=direction,
            qty=None if isna(qty) else float(qty),
            stop=None if isna(stop) else float(stop),
            limit=None if isna(limit) else float(limit)))

    def close(self, entry_id: str = "*"):
        self._queued_close = entry_id

    def cancel(self, entry_id: Optional[str] = None):
        """Cancel pending entry orders — a specific id, or all when None."""
        if entry_id is None:
            self._queued_entries = []
            self._entries = []
        else:
            self._queued_entries = [e for e in self._queued_entries if e.entry_id != entry_id]
            self._entries = [e for e in self._entries if e.entry_id != entry_id]

    def exit(self, from_entry: str = "", stop=None, limit=None, loss=None, profit=None):
        self._queued_exits = [e for e in self._queued_exits if e.from_entry != from_entry]
        self._queued_exits.append(ExitRule(
            from_entry=from_entry,
            stop=None if isna(stop) else float(stop),
            limit=None if isna(limit) else float(limit),
            loss_ticks=None if isna(loss) else float(loss),
            profit_ticks=None if isna(profit) else float(profit)))

    @property
    def position_size(self) -> float:
        if self.position is None:
            return 0.0
        return self.position.qty if self.position.direction == "long" else -self.position.qty

    def equity_at(self, price: float) -> float:
        eq = self.s.initial_capital + self.realized
        if self.position is not None:
            sign = 1.0 if self.position.direction == "long" else -1.0
            eq += sign * (price - self.position.entry_price) * self.position.qty
        return eq

    # ── bar processing ────────────────────────────────────────────────────────
    def begin_bar(self, i: int) -> None:
        """Activate orders queued on bar i-1, then run fills for bar i.
        Unfilled stop/limit entries from earlier bars stay pending; a queued
        order with the same id replaces its pending predecessor."""
        keyed = {e.entry_id: e for e in self._entries}
        for e in self._queued_entries:
            keyed[e.entry_id] = e
        self._entries = list(keyed.values())
        self._close = self._queued_close
        exit_keyed = {e.from_entry: e for e in self._exits}
        for e in self._queued_exits:
            exit_keyed[e.from_entry] = e
        self._exits = list(exit_keyed.values())
        self._queued_entries = []
        self._queued_close = None
        self._queued_exits = []

        o, h, l = self.o[i], self.h[i], self.l[i]

        # 1. Market close of the position (strategy.close)
        if self._close is not None and self.position is not None:
            if self._close == "*" or self._close == self.position.entry_id:
                self._fill_exit(i, o, "close")
            self._close = None

        # 2. Entry orders
        for order in list(self._entries):
            fill_price = self._entry_fill_price(order, o, h, l)
            if fill_price is None:
                continue  # stop/limit not reached — stays pending
            self._entries.remove(order)
            self._fill_entry(i, order, fill_price)

        # 3. Exit rules (stop-loss / take-profit) on the open position
        if self.position is not None:
            self._check_exit_rules(i, o, h, l)

        # Record what strategy.position_size reads during this bar's script run
        self.size_history.append(self.position_size)

    def end_bar(self, i: int) -> None:
        if self.s.process_orders_on_close:
            # TV `process_orders_on_close=true`: market orders placed during
            # this bar fill at this bar's CLOSE instead of the next open.
            c = float(self.c[i])
            if self._queued_close is not None and self.position is not None:
                if self._queued_close in ("*", self.position.entry_id):
                    self._close_position(i, c, "close")
                self._queued_close = None
            remaining = []
            for order in self._queued_entries:
                if order.stop is None and order.limit is None:
                    self._fill_entry(i, order, c)
                else:
                    remaining.append(order)  # stop/limit orders stay price-triggered
            self._queued_entries = remaining
        self.equity_curve.append(self.equity_at(self.c[i]))

    def finish(self, last_bar: int) -> None:
        """Close any open position at the final close."""
        if self.position is not None:
            self._close_position(last_bar, self.c[last_bar], "end_of_data")

    # ── fill mechanics ────────────────────────────────────────────────────────
    def _entry_fill_price(self, order: EntryOrder, o, h, l) -> Optional[float]:
        if order.stop is None and order.limit is None:
            return o  # market
        if order.direction == "long":
            if order.stop is not None:
                if o >= order.stop:
                    return o
                if h >= order.stop:
                    return order.stop
                return None
            if o <= order.limit:
                return o
            if l <= order.limit:
                return order.limit
            return None
        else:
            if order.stop is not None:
                if o <= order.stop:
                    return o
                if l <= order.stop:
                    return order.stop
                return None
            if o >= order.limit:
                return o
            if h >= order.limit:
                return order.limit
            return None

    def _fill_entry(self, i: int, order: EntryOrder, price: float) -> None:
        if self.position is not None:
            if self.position.direction == order.direction:
                return  # pyramiding = 1
            self._close_position(i, price, "reverse")
        qty = order.qty if order.qty is not None else self._sized_qty(price)
        if qty <= 0:
            return
        self.realized -= self._commission(price, qty)
        self.position = Position(direction=order.direction, qty=qty,
                                 entry_price=price, entry_bar=i,
                                 entry_id=order.entry_id)

    def _sized_qty(self, price: float) -> float:
        s = self.s
        if s.default_qty_type == "percent_of_equity":
            cash = self.equity_at(price) * s.default_qty_value / 100.0
            return max(cash / price, 0.0)
        if s.default_qty_type == "cash":
            return max(s.default_qty_value / price, 0.0)
        return s.default_qty_value  # fixed contracts

    def _commission(self, price: float, qty: float) -> float:
        s = self.s
        if s.commission_type == "percent":
            return price * qty * s.commission_value / 100.0
        if s.commission_type == "cash_per_contract":
            return s.commission_value * qty
        if s.commission_type == "cash_per_order":
            return s.commission_value
        return 0.0

    def _check_exit_rules(self, i: int, o, h, l) -> None:
        pos = self.position
        rule = None
        for r in self._exits:
            if r.from_entry in ("", pos.entry_id):
                rule = r
                break
        if rule is None:
            return

        sign = 1.0 if pos.direction == "long" else -1.0
        stop = rule.stop
        limit = rule.limit
        if rule.loss_ticks is not None:
            stop = pos.entry_price - sign * rule.loss_ticks * self.s.tick_size
        if rule.profit_ticks is not None:
            limit = pos.entry_price + sign * rule.profit_ticks * self.s.tick_size

        stop_hit = stop is not None and (l <= stop if sign > 0 else h >= stop)
        limit_hit = limit is not None and (h >= limit if sign > 0 else l <= limit)

        if not stop_hit and not limit_hit:
            return
        if stop_hit and limit_hit:
            # Intra-bar path heuristic (TV): open nearer the high → price went
            # open→high→low→close ("up" first), else open→low→high→close.
            first = "up" if (h - o) <= (o - l) else "down"
            if sign > 0:
                reason, price = (("limit", limit) if first == "up" else ("stop", stop))
            else:
                reason, price = (("stop", stop) if first == "up" else ("limit", limit))
        elif stop_hit:
            # Gap through the stop fills at the open
            gapped = (o <= stop) if sign > 0 else (o >= stop)
            reason, price = "stop", (o if gapped else stop)
        else:
            gapped = (o >= limit) if sign > 0 else (o <= limit)
            reason, price = "limit", (o if gapped else limit)

        self._fill_exit(i, price, reason)

    def _fill_exit(self, i: int, price: float, reason: str) -> None:
        self._close_position(i, price, reason)

    def _close_position(self, i: int, price: float, reason: str) -> None:
        pos = self.position
        sign = 1.0 if pos.direction == "long" else -1.0
        gross = sign * (price - pos.entry_price) * pos.qty
        fee = self._commission(price, pos.qty)
        # Entry commission was already deducted from `realized` at entry time;
        # attribute it to the trade record for TV-style per-trade net profit.
        entry_fee = self._commission(pos.entry_price, pos.qty)
        net = gross - fee - entry_fee
        self.realized += gross - fee
        self.closed.append(ClosedTrade(
            entry_bar=pos.entry_bar, exit_bar=i, direction=pos.direction,
            entry_price=pos.entry_price, exit_price=price, qty=pos.qty,
            profit=net, entry_id=pos.entry_id, exit_reason=reason))
        self.position = None
        self._exits = []

    # ── metrics (TradingView Strategy Tester "Overview") ────────────────────
    def metrics(self) -> dict:
        profits = [t.profit for t in self.closed]
        wins = [p for p in profits if p > 0]
        losses = [p for p in profits if p <= 0]
        gross_profit = float(sum(wins))
        gross_loss = float(abs(sum(losses)))
        net = gross_profit - gross_loss

        eq = np.array(self.equity_curve, dtype=float) if self.equity_curve else np.array([self.s.initial_capital])
        peak = np.maximum.accumulate(eq)
        dd = peak - eq
        max_dd = float(dd.max()) if len(dd) else 0.0
        with np.errstate(divide="ignore", invalid="ignore"):
            dd_pct = np.where(peak > 0, dd / peak * 100.0, 0.0)
        max_dd_pct = float(dd_pct.max()) if len(dd) else 0.0

        n = len(profits)
        open_pl = 0.0
        if self.position is not None and len(self.c):
            sign = 1.0 if self.position.direction == "long" else -1.0
            open_pl = sign * (self.c[-1] - self.position.entry_price) * self.position.qty

        return {
            "net_profit": round(net, 2),
            "net_profit_pct": round(net / self.s.initial_capital * 100.0, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss > 0 else None,
            "max_drawdown": round(max_dd, 2),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "total_trades": n,
            "percent_profitable": round(len(wins) / n * 100.0, 2) if n else None,
            "avg_trade": round(net / n, 2) if n else None,
            "avg_win": round(gross_profit / len(wins), 2) if wins else None,
            "avg_loss": round(gross_loss / len(losses), 2) if losses else None,
            "open_pl": round(open_pl, 2),
        }
