"""
My Custom Strategy — Multi-TF EMA Confluence

Entry conditions (ALL must be true):
  1. Trend aligned on 3 TFs: EMA 34 > EMA 89 on Daily (H4 resample) + H4 + H1
  2. StochRSI K was < stochrsi_buy (20) within stochrsi_lookback_bars M15 bars (oversold pullback) [buy]
               K was > stochrsi_sell (70) within stochrsi_lookback_bars M15 bars (overbought peak) [sell]
  3. MACD histogram just crossed zero on M15 (positive flip = buy) — entry trigger
  4. Price within sr_tolerance_atr × ATR of a validated S/R level (3+ H4 touches)

SL = entry ∓ sl_atr_mult × ATR (M15)
TP = entry ± tp_atr_mult × ATR (M15)

Stepped SL ("zero risk"):
  25% to TP → SL moves to break-even
  50% to TP → SL locks at +25% of TP distance

Daily bars are derived from H4 resampled to calendar days; previous day's EMA
is used (shift 1) so no same-day look-ahead is introduced.
"""
from typing import Optional
import numpy as np
import pandas as pd
from .base import BaseStrategy, Signal
from indicators import ema, atr as compute_atr, stoch_rsi, macd
from config import MyStrategyParams, SharedParams


class MyStrategy(BaseStrategy):

    def __init__(self, params: MyStrategyParams, shared: SharedParams):
        self.p = params
        self.shared = shared
        self.exec_tf = "M15"
        self._last_signal_bar: Optional[pd.Timestamp] = None

    # ── S/R helpers ────────────────────────────────────────────────────────────

    def _find_sr_levels(self, h4: pd.DataFrame, atr_val: float) -> list:
        """S/R levels from H4 swing highs/lows with ≥ sr_min_touches touches.

        Uses a centered rolling window (±5 bars), which introduces minor look-ahead
        at the trailing edge of the slice (last 5 H4 bars). Callers should pass
        h4.loc[:signal_time] to bound this to historically-available data.
        """
        p = self.p
        h4 = h4.tail(p.sr_lookback)
        if len(h4) < 20 or atr_val == 0:
            return []

        # Swing highs/lows — ±5 bar centered window
        window = 11
        swing_high_mask = h4['high'] == h4['high'].rolling(window, center=True, min_periods=6).max()
        swing_low_mask  = h4['low']  == h4['low'].rolling(window, center=True, min_periods=6).min()

        raw_levels = list(h4.loc[swing_high_mask, 'high']) + list(h4.loc[swing_low_mask, 'low'])
        if not raw_levels:
            return []

        # Cluster levels within 0.3×ATR
        tol = 0.3 * atr_val
        clusters: list[dict] = []
        for level in sorted(raw_levels):
            merged = False
            for c in clusters:
                if abs(level - c['center']) <= tol:
                    c['prices'].append(level)
                    c['center'] = sum(c['prices']) / len(c['prices'])
                    merged = True
                    break
            if not merged:
                clusters.append({'center': level, 'prices': [level]})

        # Keep only clusters with enough H4 bar touches
        touch_band = 0.3 * atr_val
        valid = []
        for c in clusters:
            center = c['center']
            touches = int(
                ((h4['low'] <= center + touch_band) & (h4['high'] >= center - touch_band)).sum()
            )
            if touches >= p.sr_min_touches:
                valid.append(center)

        return valid

    def _near_sr(self, price: float, levels: list, atr_val: float) -> bool:
        """True if price is within sr_tolerance_atr×ATR of any level, or no levels found."""
        if not levels:
            return True  # insufficient H4 history — don't block trading
        band = self.p.sr_tolerance_atr * atr_val
        return any(abs(price - lv) <= band for lv in levels)

    # ── Vectorized path ────────────────────────────────────────────────────────

    def generate_signals(self, dfs: dict) -> pd.DataFrame:
        p = self.p
        m15 = dfs["M15"].copy()
        h1  = dfs["H1"].copy()
        h4  = dfs["H4"].copy()

        warmup = p.ema_slow + 10
        if len(m15) < warmup or len(h1) < warmup or len(h4) < warmup:
            return pd.DataFrame()

        # ── Daily trend from H4 resample ─────────────────────────────────
        # shift(1): yesterday's confirmed close → no same-day look-ahead
        daily = h4.resample('D').agg(
            {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
        ).dropna()
        if len(daily) < p.ema_slow + 2:
            return pd.DataFrame()
        ema_f_d = ema(daily['close'], p.ema_fast)
        ema_s_d = ema(daily['close'], p.ema_slow)
        daily_bull = (ema_f_d > ema_s_d).shift(1).reindex(m15.index, method='ffill').fillna(False)
        daily_bear = (ema_f_d < ema_s_d).shift(1).reindex(m15.index, method='ffill').fillna(False)

        # ── H4 trend ─────────────────────────────────────────────────────
        ema_f_h4 = ema(h4['close'], p.ema_fast)
        ema_s_h4 = ema(h4['close'], p.ema_slow)
        h4_bull = (ema_f_h4 > ema_s_h4).reindex(m15.index, method='ffill').fillna(False)
        h4_bear = (ema_f_h4 < ema_s_h4).reindex(m15.index, method='ffill').fillna(False)

        # ── H1 trend + crossover recency ──────────────────────────────────
        ema_f_h1 = ema(h1['close'], p.ema_fast)
        ema_s_h1 = ema(h1['close'], p.ema_slow)
        h1_bull = (ema_f_h1 > ema_s_h1).reindex(m15.index, method='ffill').fillna(False)
        h1_bear = (ema_f_h1 < ema_s_h1).reindex(m15.index, method='ffill').fillna(False)

        # ── Trend agreement (all 3 TFs) ───────────────────────────────────
        trend_bull = daily_bull & h4_bull & h1_bull
        trend_bear = daily_bear & h4_bear & h1_bear

        # ── StochRSI on M15 (sequential: oversold within lookback window) ───
        # Same-bar conjunction of StochRSI extreme + MACD zero-cross is empirically
        # empty (~0 co-occurrences in 77k bars): price bottoms first, then MACD
        # histogram recovers N bars later. Use a rolling window to capture the
        # pullback phase; MACD zero-cross remains the exact entry trigger.
        srsi_k, _ = stoch_rsi(m15['close'], p.stochrsi_period, p.stochrsi_k, p.stochrsi_d)
        stoch_buy  = (srsi_k < p.stochrsi_buy).rolling(p.stochrsi_lookback_bars, min_periods=1).max().astype(bool)
        stoch_sell = (srsi_k > p.stochrsi_sell).rolling(p.stochrsi_lookback_bars, min_periods=1).max().astype(bool)

        # ── MACD histogram zero-cross on M15 (entry trigger) ─────────────
        _, _, hist = macd(m15['close'], p.macd_fast, p.macd_slow, p.macd_signal_period)
        macd_buy  = (hist > 0) & (hist.shift(1) <= 0)
        macd_sell = (hist < 0) & (hist.shift(1) >= 0)

        # ── Combined entry mask ───────────────────────────────────────────
        buy_mask  = trend_bull & stoch_buy  & macd_buy
        sell_mask = trend_bear & stoch_sell & macd_sell
        signal_mask = buy_mask | sell_mask
        if not signal_mask.any():
            return pd.DataFrame()

        # ── ATR (M15) ─────────────────────────────────────────────────────
        atr_m15 = compute_atr(m15['high'], m15['low'], m15['close'], p.atr_period)
        atr_fallback = float(atr_m15.dropna().median()) if atr_m15.notna().any() else 1.0

        # ── H4 ATR for S/R tolerance ──────────────────────────────────────
        atr_h4_series = compute_atr(h4['high'], h4['low'], h4['close'], p.atr_period)

        rows, indices = [], []
        for idx in m15.index[signal_mask]:
            direction = 'buy' if buy_mask[idx] else 'sell'
            entry = float(m15.at[idx, 'close'])
            atr   = float(atr_m15[idx]) if not np.isnan(atr_m15[idx]) else atr_fallback

            # S/R: slice H4 to only bars available at this signal time
            if p.require_sr:
                h4_slice = h4.loc[:idx]
                atr_h4_val = float(atr_h4_series.loc[:idx].dropna().iloc[-1]) if len(h4_slice) >= p.atr_period else atr
                levels = self._find_sr_levels(h4_slice, atr_h4_val)
                if not self._near_sr(entry, levels, atr):
                    continue

            sl = (entry - p.sl_atr_mult * atr) if direction == 'buy' else (entry + p.sl_atr_mult * atr)
            tp = (entry + p.tp_atr_mult * atr) if direction == 'buy' else (entry - p.tp_atr_mult * atr)
            rows.append({'direction': direction, 'entry': entry, 'sl': sl, 'tp': tp, 'atr': atr})
            indices.append(idx)

        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows, index=pd.DatetimeIndex(indices))

    # ── Incremental path ───────────────────────────────────────────────────────

    def get_signal(self, dfs: dict) -> Optional[Signal]:
        p = self.p
        m15 = dfs["M15"]
        h1  = dfs["H1"]
        h4  = dfs["H4"]

        warmup = p.ema_slow + 10
        if len(m15) < warmup or len(h1) < warmup or len(h4) < warmup:
            return None

        current_bar = m15.index[-1]
        if self._last_signal_bar == current_bar:
            return None

        # ── Daily trend: use yesterday's confirmed close ───────────────────
        daily = h4.resample('D').agg(
            {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
        ).dropna()
        if len(daily) < p.ema_slow + 2:
            return None
        # exclude today's incomplete bar
        daily_confirmed = daily.iloc[:-1]
        ema_f_d_val = float(ema(daily_confirmed['close'], p.ema_fast).iloc[-1])
        ema_s_d_val = float(ema(daily_confirmed['close'], p.ema_slow).iloc[-1])
        daily_up = ema_f_d_val > ema_s_d_val
        daily_dn = ema_f_d_val < ema_s_d_val

        # ── H4 trend ─────────────────────────────────────────────────────
        ema_f_h4_val = float(ema(h4['close'], p.ema_fast).iloc[-1])
        ema_s_h4_val = float(ema(h4['close'], p.ema_slow).iloc[-1])
        h4_up = ema_f_h4_val > ema_s_h4_val
        h4_dn = ema_f_h4_val < ema_s_h4_val

        # ── H1 trend ─────────────────────────────────────────────────────
        ema_f_h1 = ema(h1['close'], p.ema_fast)
        ema_s_h1 = ema(h1['close'], p.ema_slow)
        h1_up = float(ema_f_h1.iloc[-1]) > float(ema_s_h1.iloc[-1])
        h1_dn = float(ema_f_h1.iloc[-1]) < float(ema_s_h1.iloc[-1])

        trend_bull = daily_up and h4_up and h1_up
        trend_bear = daily_dn and h4_dn and h1_dn
        if not (trend_bull or trend_bear):
            return None

        # ── StochRSI on M15 (sequential: was extreme within lookback window) ─
        srsi_k, _ = stoch_rsi(m15['close'], p.stochrsi_period, p.stochrsi_k, p.stochrsi_d)
        k_window = srsi_k.iloc[-p.stochrsi_lookback_bars:]
        if k_window.isna().all():
            return None
        stoch_buy_ok  = bool((k_window < p.stochrsi_buy).any())
        stoch_sell_ok = bool((k_window > p.stochrsi_sell).any())
        if trend_bull and not stoch_buy_ok:
            return None
        if trend_bear and not stoch_sell_ok:
            return None

        # ── MACD histogram zero-cross on M15 ─────────────────────────────
        _, _, hist = macd(m15['close'], p.macd_fast, p.macd_slow, p.macd_signal_period)
        h_cur  = float(hist.iloc[-1])
        h_prev = float(hist.iloc[-2])
        if np.isnan(h_cur) or np.isnan(h_prev):
            return None
        if trend_bull and not (h_cur > 0 and h_prev <= 0):
            return None
        if trend_bear and not (h_cur < 0 and h_prev >= 0):
            return None

        # ── ATR (M15) ─────────────────────────────────────────────────────
        atr_series = compute_atr(m15['high'], m15['low'], m15['close'], p.atr_period)
        atr_val = float(atr_series.dropna().iloc[-1])
        if atr_val == 0 or np.isnan(atr_val):
            return None

        entry = float(m15['close'].iloc[-1])

        # ── S/R proximity ─────────────────────────────────────────────────
        if p.require_sr:
            atr_h4_series = compute_atr(h4['high'], h4['low'], h4['close'], p.atr_period)
            atr_h4_val = float(atr_h4_series.dropna().iloc[-1])
            levels = self._find_sr_levels(h4, atr_h4_val)
            if not self._near_sr(entry, levels, atr_val):
                return None

        direction = 'buy' if trend_bull else 'sell'
        sl = (entry - p.sl_atr_mult * atr_val) if direction == 'buy' else (entry + p.sl_atr_mult * atr_val)
        tp = (entry + p.tp_atr_mult * atr_val) if direction == 'buy' else (entry - p.tp_atr_mult * atr_val)

        self._last_signal_bar = current_bar
        return Signal(direction, entry, sl, tp, atr_val, current_bar)

    # ── Indicator snapshot for replay UI ──────────────────────────────────────

    def get_indicators(self, dfs: dict) -> dict:
        p = self.p
        m15 = dfs.get("M15")
        h1  = dfs.get("H1")
        h4  = dfs.get("H4")
        if m15 is None or h1 is None or h4 is None:
            return {}
        warmup = p.ema_slow + 10
        if len(m15) < warmup or len(h1) < warmup or len(h4) < warmup:
            return {}

        daily = h4.resample('D').agg(
            {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
        ).dropna()

        ema_f_d = ema(daily['close'], p.ema_fast) if len(daily) >= p.ema_slow else None
        ema_s_d = ema(daily['close'], p.ema_slow) if len(daily) >= p.ema_slow else None
        ema_f_h4 = ema(h4['close'], p.ema_fast)
        ema_s_h4 = ema(h4['close'], p.ema_slow)
        ema_f_h1 = ema(h1['close'], p.ema_fast)
        ema_s_h1 = ema(h1['close'], p.ema_slow)
        atr_m15 = compute_atr(m15['high'], m15['low'], m15['close'], p.atr_period)
        srsi_k, srsi_d = stoch_rsi(m15['close'], p.stochrsi_period, p.stochrsi_k, p.stochrsi_d)
        _, _, hist = macd(m15['close'], p.macd_fast, p.macd_slow, p.macd_signal_period)

        def safe(series, decimals=2):
            if series is None:
                return None
            v = float(series.iloc[-1])
            return round(v, decimals) if not np.isnan(v) else None

        return {
            'ema34_daily':  safe(ema_f_d),
            'ema89_daily':  safe(ema_s_d),
            'ema34_h4':     safe(ema_f_h4),
            'ema89_h4':     safe(ema_s_h4),
            'ema34_h1':     safe(ema_f_h1),
            'ema89_h1':     safe(ema_s_h1),
            'stochrsi_k':   safe(srsi_k),
            'stochrsi_d':   safe(srsi_d),
            'macd_hist':    safe(hist, 4),
            'atr_m15':      safe(atr_m15),
        }
