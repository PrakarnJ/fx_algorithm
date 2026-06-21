from typing import Optional
import numpy as np
import pandas as pd
from .base import BaseStrategy, Signal
from indicators import rsi, atr
from config import MeanReversionParams, SharedParams


class MeanReversionStrategy(BaseStrategy):
    """
    Z-score fade: when price stretches z_entry standard deviations from its
    rolling mean, fade the move back toward the mean with a fixed-point
    TP/SL scalp. Optional RSI-extreme confirmation and session gate.

    With manage_trail=False the signal's atr is emitted as 0, which disables
    trade_manager.update_sl in the engine — pure fixed SL/TP behaviour.
    """

    def __init__(self, params: MeanReversionParams, shared: SharedParams):
        self.p = params
        self.shared = shared
        self.exec_tf = params.tf
        self._last_signal_bar: Optional[pd.Timestamp] = None

    # ── shared condition logic ────────────────────────────────────────────
    def _z_stats(self, bars: pd.DataFrame):
        close = bars["close"]
        mean = close.rolling(self.p.z_lookback).mean()
        std = close.rolling(self.p.z_lookback).std().replace(0, np.nan)
        return (close - mean) / std, mean

    def _masks(self, bars: pd.DataFrame):
        z, _ = self._z_stats(bars)

        buy_mask = z < -self.p.z_entry
        sell_mask = z > self.p.z_entry

        if self.p.rsi_confirm:
            r = rsi(bars["close"], self.p.rsi_period)
            buy_mask &= r < self.p.rsi_extreme
            sell_mask &= r > 100 - self.p.rsi_extreme

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

    # ── vectorized path (backtest) ────────────────────────────────────────
    def generate_signals(self, dfs: dict) -> pd.DataFrame:
        bars = dfs[self.p.tf]
        buy_mask, sell_mask = self._masks(bars)

        # Edge-trigger: only the first bar of a stretch
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

    # ── incremental path (live bot) ───────────────────────────────────────
    def get_signal(self, dfs: dict) -> Optional[Signal]:
        bars = dfs[self.p.tf]
        if len(bars) < self.p.z_lookback + 10:
            return None

        current_bar = bars.index[-1]
        if self._last_signal_bar == current_bar:
            return None

        buy_mask, sell_mask = self._masks(bars)
        is_buy, is_sell = bool(buy_mask.iloc[-1]), bool(sell_mask.iloc[-1])
        if not (is_buy or is_sell):
            return None
        # Edge-trigger parity with generate_signals
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

    def get_indicators(self, dfs: dict) -> dict:
        bars = dfs.get(self.p.tf)
        if bars is None or len(bars) < self.p.z_lookback:
            return {}
        z_series, mean_series = self._z_stats(bars)
        z_val = float(z_series.iloc[-1])
        if pd.isna(z_val):
            z_val = 0.0
        result = {"z_score": round(z_val, 3), "rolling_mean": round(float(mean_series.iloc[-1]), 4)}
        if self.p.rsi_confirm:
            result["rsi"] = round(float(rsi(bars["close"], self.p.rsi_period).iloc[-1]), 2)
        if self.p.manage_trail:
            h1 = dfs.get("H1")
            if h1 is not None:
                result["atr"] = round(float(atr(h1["high"], h1["low"], h1["close"], 14).iloc[-1]), 4)
        return result
