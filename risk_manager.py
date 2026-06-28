from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from config import SharedParams


def calculate_lot(
    balance: float,
    risk_pct: float,
    sl_distance: float,
    symbol_info,
) -> float:
    """
    Returns lot size so that (sl_distance * lot) risk == risk_pct * balance.
    symbol_info is any object with attrs: trade_tick_value, trade_tick_size,
    volume_min, volume_step, volume_max.
    """
    risk_amount = balance * risk_pct
    tick_value = symbol_info.trade_tick_value
    tick_size = symbol_info.trade_tick_size

    if tick_size == 0 or sl_distance == 0:
        return symbol_info.volume_min

    value_per_lot_per_point = tick_value / tick_size
    if value_per_lot_per_point == 0:
        return symbol_info.volume_min

    lot = risk_amount / (sl_distance * value_per_lot_per_point)
    step = symbol_info.volume_step
    lot = round(lot / step) * step
    lot = max(symbol_info.volume_min, min(lot, symbol_info.volume_max))
    return lot


class DrawdownGuard:
    def __init__(self, params: SharedParams):
        self.p = params
        self._consec_losses: int = 0
        self._pause_until: Optional[datetime] = None
        self._session_open_balance: Optional[float] = None

    def set_session_balance(self, balance: float) -> None:
        if self._session_open_balance is None:
            self._session_open_balance = balance

    def record_result(self, profit: float, now: datetime) -> None:
        if profit < 0:
            self._consec_losses += 1
            if self._consec_losses >= self.p.max_consec_losses:
                self._pause_until = now + timedelta(hours=self.p.consec_loss_pause_hours)
                self._consec_losses = 0
        else:
            self._consec_losses = 0

    def is_allowed(self, current_balance: float, now: datetime) -> bool:
        if self._pause_until and now < self._pause_until:
            return False
        if self._session_open_balance is not None:
            day_loss_pct = (self._session_open_balance - current_balance) / self._session_open_balance
            if day_loss_pct >= self.p.daily_loss_stop_pct:
                return False
        return True

    def reset_daily(self) -> None:
        self._session_open_balance = None
