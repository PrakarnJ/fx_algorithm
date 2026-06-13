from typing import Optional
import numpy as np
import pandas as pd
from .base import BaseStrategy, Signal
from indicators import rsi, ema, atr
from config import RsiFadeParams, SharedParams


class RsiFadeStrategy(BaseStrategy):
    """
    Short-period RSI extreme fade: buy when RSI(n) collapses below buy_below,
    sell when it spikes above sell_above. Fixed-point TP/SL scalp.

    trend_gate=True only takes fades that revert toward the H1 EMA(50):
    buys only when price is below the EMA (stretched down), sells only above.
    """

    def __init__(self, params: RsiFadeParams, shared: SharedParams):
        self.p = params
        self.shared = shared
        self.exec_tf = params.tf
        self._last_signal_bar: Optional[pd.Timestamp] = None

    def _masks(self, dfs: dict, bars: pd.DataFrame):
        close = bars["close"]
        r = rsi(close, self.p.rsi_period)
        buy_mask = r < self.p.buy_below
        sell_mask = r > self.p.sell_above

        if self.p.trend_gate:
            h1 = dfs["H1"]
            ema_h1 = ema(h1["close"], 50).reindex(bars.index, method="ffill")
            buy_mask &= close < ema_h1
            sell_mask &= close > ema_h1

        if not (self.p.session_start == 0 and self.p.session_end == 24):
            hours = bars.index.hour
            in_session = (hours >= self.p.session_start) & (hours < self.p.session_end)
            buy_mask &= in_session
            sell_mask &= in_session

        return buy_mask.fillna(False), sell_mask.fillna(False)

    def _atr_on_bars(self, dfs: dict, bars: pd.DataFrame) -> pd.Series:
        h1 = dfs["H1"]
        atr_h1 = atr(h1["high"], h1["low"], h1["close"], 14)
        return atr_h1.reindex(bars.index, method="ffill")

    def generate_signals(self, dfs: dict) -> pd.DataFrame:
        bars = dfs[self.p.tf]
        buy_mask, sell_mask = self._masks(dfs, bars)

        any_mask = buy_mask | sell_mask
        fresh = any_mask & ~any_mask.shift(1, fill_value=False)
        cand_idx = np.flatnonzero(fresh.values)

        atr_series = self._atr_on_bars(dfs, bars) if self.p.manage_trail else None
        closes = bars["close"].values
        buy_arr = buy_mask.values

        rows = []
        last_i = -10**9
        for i in cand_idx:
            if i - last_i < self.p.cooldown_bars:
                continue
            last_i = i
            entry = closes[i]
            if buy_arr[i]:
                sl, tp, direction = entry - self.p.sl_pts, entry + self.p.tp_pts, "buy"
            else:
                sl, tp, direction = entry + self.p.sl_pts, entry - self.p.tp_pts, "sell"
            atr_val = float(atr_series.iloc[i]) if atr_series is not None else 0.0
            if atr_series is not None and pd.isna(atr_val):
                atr_val = 0.0
            rows.append(dict(
                time=bars.index[i], direction=direction,
                entry=entry, sl=sl, tp=tp, atr=atr_val,
            ))

        cols = ["direction", "entry", "sl", "tp", "atr"]
        if not rows:
            return pd.DataFrame(columns=cols)
        return pd.DataFrame(rows).set_index("time")[cols]

    def get_signal(self, dfs: dict) -> Optional[Signal]:
        bars = dfs[self.p.tf]
        if len(bars) < max(self.p.rsi_period + 10, 60):
            return None

        current_bar = bars.index[-1]
        if self._last_signal_bar == current_bar:
            return None

        buy_mask, sell_mask = self._masks(dfs, bars)
        is_buy, is_sell = bool(buy_mask.iloc[-1]), bool(sell_mask.iloc[-1])
        if not (is_buy or is_sell):
            return None
        if bool((buy_mask | sell_mask).iloc[-2]):
            return None

        entry = float(bars["close"].iloc[-1])
        atr_val = 0.0
        if self.p.manage_trail:
            atr_val = float(self._atr_on_bars(dfs, bars).iloc[-1] or 0.0)

        if is_buy:
            signal = Signal("buy", entry, entry - self.p.sl_pts,
                            entry + self.p.tp_pts, atr_val, current_bar)
        else:
            signal = Signal("sell", entry, entry + self.p.sl_pts,
                            entry - self.p.tp_pts, atr_val, current_bar)

        self._last_signal_bar = current_bar
        return signal
