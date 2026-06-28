"""
Pullback Scalper — EMA(21) touch in a trending market.

Entry: H1 trending (ADX > 20, EMA50 sloping) + M15 price touches EMA(21)
       + RSI(14) in 35–55 zone (moderate pullback, not extreme).
       Session-gated to London + NY (07:00–17:00 UTC).

SL: 1.5 × ATR(14) on M15
TP: 3.0 × ATR(14) on M15  →  2:1 R:R
Cooldown: 8 M15 bars (2 hours) between signals.
"""
from typing import Optional
import numpy as np
import pandas as pd
from .base import BaseStrategy, Signal
from indicators import ema, rsi, atr as compute_atr, adx as compute_adx
from config import PullbackScalperParams, SharedParams


class PullbackScalperStrategy(BaseStrategy):

    def __init__(self, params: PullbackScalperParams, shared: SharedParams):
        self.p = params
        self.shared = shared
        self.exec_tf = "M15"
        self._last_signal_bar: Optional[pd.Timestamp] = None

    # ── Vectorized path ────────────────────────────────────────────────────────

    def generate_signals(self, dfs: dict) -> pd.DataFrame:
        p = self.p
        m15 = dfs["M15"]
        h1  = dfs["H1"]

        warmup = max(p.ema_trend, p.adx_period * 2, p.ema_entry, p.rsi_period) + 10
        if len(m15) < warmup or len(h1) < warmup:
            return pd.DataFrame(columns=["direction", "entry", "sl", "tp", "atr"])

        # ── H1 trend indicators → reindex to M15 with ffill ──────────────
        ema50_h1  = ema(h1["close"], p.ema_trend)
        slope_up  = (ema50_h1 > ema50_h1.shift(p.ema_slope_lookback)).reindex(m15.index, method="ffill").fillna(False)
        slope_dn  = (ema50_h1 < ema50_h1.shift(p.ema_slope_lookback)).reindex(m15.index, method="ffill").fillna(False)
        h1_bull   = (h1["close"] > ema50_h1).reindex(m15.index, method="ffill").fillna(False)
        h1_bear   = (h1["close"] < ema50_h1).reindex(m15.index, method="ffill").fillna(False)
        adx_h1    = compute_adx(h1["high"], h1["low"], h1["close"], p.adx_period)
        trending  = (adx_h1 > p.adx_min).reindex(m15.index, method="ffill").fillna(False)

        # ── M15 indicators ────────────────────────────────────────────────
        ema21_m15 = ema(m15["close"], p.ema_entry)
        atr_m15   = compute_atr(m15["high"], m15["low"], m15["close"], p.atr_period)
        near_ema  = (m15["close"] - ema21_m15).abs() <= p.ema_touch_atr * atr_m15
        rsi_m15   = rsi(m15["close"], p.rsi_period)
        rsi_buy   = rsi_m15.between(p.rsi_buy_lo, p.rsi_buy_hi)
        rsi_sell  = rsi_m15.between(p.rsi_sell_lo, p.rsi_sell_hi)

        # ── Session gate ──────────────────────────────────────────────────
        in_session = (m15.index.hour >= p.session_start) & (m15.index.hour < p.session_end)

        # Candle-direction filter: entry bar must show momentum resuming
        bull_candle = m15["close"] > m15["open"]
        bear_candle = m15["close"] < m15["open"]

        buy_mask  = (trending & slope_up & h1_bull & near_ema & rsi_buy  & in_session & bull_candle).fillna(False)
        sell_mask = (trending & slope_dn & h1_bear & near_ema & rsi_sell & in_session & bear_candle).fillna(False)

        # Edge-trigger: only the first bar each time conditions flip on
        any_mask = buy_mask | sell_mask
        fresh = any_mask & ~any_mask.shift(1, fill_value=False)
        cand_idx = np.flatnonzero(fresh.values)

        closes  = m15["close"].values
        atr_arr = atr_m15.values
        buy_arr = buy_mask.values

        rows = []
        last_i = -(10 ** 9)
        for i in cand_idx:
            if i - last_i < p.cooldown_bars:
                continue
            atr_val = float(atr_arr[i])
            if np.isnan(atr_val) or atr_val <= 0:
                continue
            last_i = i
            entry = float(closes[i])
            if buy_arr[i]:
                sl, tp, direction = (entry - p.sl_atr_mult * atr_val,
                                     entry + p.tp_atr_mult * atr_val, "buy")
            else:
                sl, tp, direction = (entry + p.sl_atr_mult * atr_val,
                                     entry - p.tp_atr_mult * atr_val, "sell")
            rows.append(dict(time=m15.index[i], direction=direction,
                             entry=entry, sl=sl, tp=tp, atr=atr_val))

        cols = ["direction", "entry", "sl", "tp", "atr"]
        if not rows:
            return pd.DataFrame(columns=cols)
        return pd.DataFrame(rows).set_index("time")[cols]

    # ── Incremental path ───────────────────────────────────────────────────────

    def get_signal(self, dfs: dict) -> Optional[Signal]:
        p = self.p
        m15 = dfs["M15"]
        h1  = dfs["H1"]

        warmup = max(p.ema_trend, p.adx_period * 2, p.ema_entry, p.rsi_period) + 10
        if len(m15) < warmup or len(h1) < warmup:
            return None

        current_bar = m15.index[-1]
        if self._last_signal_bar == current_bar:
            return None

        # ── H1 trend ─────────────────────────────────────────────────────
        ema50_h1  = ema(h1["close"], p.ema_trend)
        h1_ema    = float(ema50_h1.iloc[-1])
        h1_close  = float(h1["close"].iloc[-1])
        slope_val = float(ema50_h1.iloc[-1]) - float(ema50_h1.iloc[-(p.ema_slope_lookback + 1)])
        adx_val   = float(compute_adx(h1["high"], h1["low"], h1["close"], p.adx_period).iloc[-1])

        if np.isnan(adx_val) or adx_val < p.adx_min:
            return None

        trend_bull = slope_val > 0 and h1_close > h1_ema
        trend_bear = slope_val < 0 and h1_close < h1_ema
        if not (trend_bull or trend_bear):
            return None

        # ── M15 entry conditions ──────────────────────────────────────────
        hour = current_bar.hour
        if not (p.session_start <= hour < p.session_end):
            return None

        ema21_val = float(ema(m15["close"], p.ema_entry).iloc[-1])
        atr_val   = float(compute_atr(m15["high"], m15["low"], m15["close"], p.atr_period).dropna().iloc[-1])
        if atr_val <= 0 or np.isnan(atr_val):
            return None

        close_val = float(m15["close"].iloc[-1])
        if abs(close_val - ema21_val) > p.ema_touch_atr * atr_val:
            return None

        rsi_val = float(rsi(m15["close"], p.rsi_period).iloc[-1])
        if np.isnan(rsi_val):
            return None

        if trend_bull and not (p.rsi_buy_lo <= rsi_val <= p.rsi_buy_hi):
            return None
        if trend_bear and not (p.rsi_sell_lo <= rsi_val <= p.rsi_sell_hi):
            return None

        # Candle-direction: entry bar must show momentum resuming
        open_val = float(m15["open"].iloc[-1])
        if trend_bull and not (close_val > open_val):
            return None
        if trend_bear and not (close_val < open_val):
            return None

        direction = "buy" if trend_bull else "sell"
        entry = close_val
        sl = (entry - p.sl_atr_mult * atr_val) if direction == "buy" else (entry + p.sl_atr_mult * atr_val)
        tp = (entry + p.tp_atr_mult * atr_val) if direction == "buy" else (entry - p.tp_atr_mult * atr_val)

        self._last_signal_bar = current_bar
        return Signal(direction, entry, sl, tp, atr_val, current_bar)

    # ── Indicator snapshot for replay UI ──────────────────────────────────────

    def get_indicators(self, dfs: dict) -> dict:
        p = self.p
        m15 = dfs.get("M15")
        h1  = dfs.get("H1")
        if m15 is None or h1 is None:
            return {}
        if len(m15) < p.ema_entry + 5 or len(h1) < p.ema_trend + 5:
            return {}

        def safe(v):
            return round(float(v), 4) if not np.isnan(float(v)) else None

        ema21 = ema(m15["close"], p.ema_entry).iloc[-1]
        ema50 = ema(h1["close"], p.ema_trend).iloc[-1]
        rsi_v = rsi(m15["close"], p.rsi_period).iloc[-1]
        adx_v = compute_adx(h1["high"], h1["low"], h1["close"], p.adx_period).iloc[-1]
        atr_v = compute_atr(m15["high"], m15["low"], m15["close"], p.atr_period).iloc[-1]

        return {
            "ema21_m15": safe(ema21),
            "ema50_h1":  safe(ema50),
            "rsi_m15":   safe(rsi_v),
            "adx_h1":    safe(adx_v),
            "atr_m15":   safe(atr_v),
        }
