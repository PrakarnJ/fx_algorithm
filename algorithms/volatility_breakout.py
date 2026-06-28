"""
Volatility Expansion Breakout — enter when ATR spikes above its rolling average.

Signal: M15 ATR(14) > atr_expansion × rolling_mean(ATR, 20)
        + candle direction matches H1 EMA(50) trend
        + session-gated to London + NY (07:00–17:00 UTC)

Logic: an ATR spike means a momentum burst is happening *right now*.
Entering in the direction of the H1 trend on that expansion candle rides
the burst. SL is tight (1.0 ATR) because if the move reverses immediately
the thesis is wrong; TP is 2.5 ATR (2.5:1 R:R, break-even at 29% WR).

Cooldown: 8 M15 bars (2 hours) between signals.
"""
from typing import Optional
import numpy as np
import pandas as pd
from .base import BaseStrategy, Signal
from indicators import ema, atr as compute_atr, adx as compute_adx
from config import VolatilityBreakoutParams, SharedParams


class VolatilityBreakoutStrategy(BaseStrategy):

    def __init__(self, params: VolatilityBreakoutParams, shared: SharedParams):
        self.p = params
        self.shared = shared
        self.exec_tf = "M15"
        self._last_signal_bar: Optional[pd.Timestamp] = None

    # ── Vectorized path ────────────────────────────────────────────────────────

    def generate_signals(self, dfs: dict) -> pd.DataFrame:
        p = self.p
        m15 = dfs["M15"]
        h1  = dfs["H1"]

        warmup = max(p.atr_period + p.atr_avg_period, p.ema_trend) + 10
        if len(m15) < warmup or len(h1) < warmup:
            return pd.DataFrame(columns=["direction", "entry", "sl", "tp", "atr"])

        # ── H1 trend direction + ADX → reindex to M15 ───────────────────
        ema50_h1  = ema(h1["close"], p.ema_trend)
        adx_h1    = compute_adx(h1["high"], h1["low"], h1["close"], p.adx_period)
        trending  = (adx_h1 > p.adx_min).reindex(m15.index, method="ffill").fillna(False)
        h1_bull   = (h1["close"] > ema50_h1).reindex(m15.index, method="ffill").fillna(False)
        h1_bear   = (h1["close"] < ema50_h1).reindex(m15.index, method="ffill").fillna(False)

        # ── ATR expansion on M15 ─────────────────────────────────────────
        atr_m15   = compute_atr(m15["high"], m15["low"], m15["close"], p.atr_period)
        atr_avg   = atr_m15.rolling(p.atr_avg_period, min_periods=p.atr_avg_period).mean()
        expanding = atr_m15 > p.atr_expansion * atr_avg

        # ── Candle direction + Donchian breakout confirmation ────────────
        bull_candle = m15["close"] > m15["open"]
        bear_candle = m15["close"] < m15["open"]

        if p.require_new_extreme:
            # Price must close above the prior N-bar high (buy) or below N-bar low (sell)
            # shift(1) so the current bar's high/low doesn't count itself
            prior_high = m15["high"].rolling(p.donchian_period).max().shift(1)
            prior_low  = m15["low"].rolling(p.donchian_period).min().shift(1)
            new_high   = m15["close"] >= prior_high
            new_low    = m15["close"] <= prior_low
        else:
            new_high = pd.Series(True, index=m15.index)
            new_low  = pd.Series(True, index=m15.index)

        # ── Session gate ──────────────────────────────────────────────────
        in_session = (m15.index.hour >= p.session_start) & (m15.index.hour < p.session_end)

        buy_mask  = (expanding & trending & h1_bull & bull_candle & new_high & in_session).fillna(False)
        sell_mask = (expanding & trending & h1_bear & bear_candle & new_low  & in_session).fillna(False)

        # Edge-trigger: only fire on the first bar each time conditions flip on
        any_mask = buy_mask | sell_mask
        fresh    = any_mask & ~any_mask.shift(1, fill_value=False)
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

        warmup = max(p.atr_period + p.atr_avg_period, p.ema_trend) + 10
        if len(m15) < warmup or len(h1) < warmup:
            return None

        current_bar = m15.index[-1]
        if self._last_signal_bar == current_bar:
            return None

        # ── H1 trend + ADX ───────────────────────────────────────────────
        ema50_h1 = ema(h1["close"], p.ema_trend)
        h1_close = float(h1["close"].iloc[-1])
        h1_ema   = float(ema50_h1.iloc[-1])
        adx_val  = float(compute_adx(h1["high"], h1["low"], h1["close"], p.adx_period).iloc[-1])
        if np.isnan(adx_val) or adx_val < p.adx_min:
            return None
        trend_bull = h1_close > h1_ema
        trend_bear = h1_close < h1_ema
        if not (trend_bull or trend_bear):
            return None

        # ── Session gate ──────────────────────────────────────────────────
        if not (p.session_start <= current_bar.hour < p.session_end):
            return None

        # ── ATR expansion on M15 ─────────────────────────────────────────
        atr_series = compute_atr(m15["high"], m15["low"], m15["close"], p.atr_period)
        atr_val    = float(atr_series.iloc[-1])
        atr_avg    = float(atr_series.iloc[-(p.atr_avg_period + 1):-1].mean())
        if np.isnan(atr_val) or atr_val <= 0 or np.isnan(atr_avg) or atr_avg <= 0:
            return None
        if atr_val <= p.atr_expansion * atr_avg:
            return None

        # ── Candle direction + Donchian breakout confirmation ────────────
        close_val = float(m15["close"].iloc[-1])
        open_val  = float(m15["open"].iloc[-1])
        if trend_bull and not (close_val > open_val):
            return None
        if trend_bear and not (close_val < open_val):
            return None

        if p.require_new_extreme:
            prior_slice = m15.iloc[-(p.donchian_period + 1):-1]
            prior_high = float(prior_slice["high"].max())
            prior_low  = float(prior_slice["low"].min())
            if trend_bull and close_val < prior_high:
                return None
            if trend_bear and close_val > prior_low:
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
        if len(m15) < p.atr_period + p.atr_avg_period + 5 or len(h1) < p.ema_trend + 5:
            return {}

        def safe(v):
            f = float(v)
            return round(f, 4) if not np.isnan(f) else None

        atr_series = compute_atr(m15["high"], m15["low"], m15["close"], p.atr_period)
        atr_avg    = atr_series.rolling(p.atr_avg_period).mean()
        ema50      = ema(h1["close"], p.ema_trend)
        adx_series = compute_adx(h1["high"], h1["low"], h1["close"], p.adx_period)

        return {
            "atr_m15":      safe(atr_series.iloc[-1]),
            "atr_avg_m15":  safe(atr_avg.iloc[-1]),
            "atr_ratio":    safe(atr_series.iloc[-1] / atr_avg.iloc[-1]) if float(atr_avg.iloc[-1]) > 0 else None,
            "ema50_h1":     safe(ema50.iloc[-1]),
            "adx_h1":       safe(adx_series.iloc[-1]),
        }
