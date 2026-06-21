from typing import Optional
import numpy as np
import pandas as pd
from .base import BaseStrategy, Signal
from indicators import ema, atr
from config import TrendBreakoutParams, SharedParams
from backtest.regime import classify_regime


class TrendBreakoutStrategy(BaseStrategy):
    """
    Trend-following: enter WITH the move and ride it with an ATR trailing
    stop (no fixed take-profit — TP is set far away so the trailing stop in
    trade_manager.update_sl does the exiting).

    mode='donchian':     long on close > N-bar high, short on close < N-bar low.
    mode='ma_momentum':  long when EMA_fast > EMA_slow and both rising.

    The signal carries a real atr so the engine trails; sl is a wide initial
    stop. With regime_filter the strategy only enters when the higher-timeframe
    regime agrees with the trade direction — the lesson from the fade campaign:
    only trade trends when the market is actually trending.
    """

    FAR_TP = 1e6  # effectively no fixed TP; trailing stop governs the exit

    def __init__(self, params: TrendBreakoutParams, shared: SharedParams):
        self.p = params
        self.shared = shared
        self.exec_tf = params.tf
        self._last_signal_bar: Optional[pd.Timestamp] = None

    def _atr_series(self, bars: pd.DataFrame) -> pd.Series:
        return atr(bars["high"], bars["low"], bars["close"], self.p.atr_period)

    # ── entry masks ────────────────────────────────────────────────────────
    def _entry(self, dfs: dict, bars: pd.DataFrame):
        close = bars["close"]
        atr_val = self._atr_series(bars)

        if self.p.mode == "donchian":
            n = self.p.channel_period
            # prior-bar channel (shifted) — breakout of the *previous* window
            hh = bars["high"].rolling(n).max().shift(1)
            ll = bars["low"].rolling(n).min().shift(1)
            long_mask = close > hh
            short_mask = close < ll
        else:  # ma_momentum
            ef = ema(close, self.p.ema_fast)
            es = ema(close, self.p.ema_slow)
            rising = ef > ef.shift(self.p.slope_lookback)
            falling = ef < ef.shift(self.p.slope_lookback)
            long_mask = (ef > es) & rising
            short_mask = (ef < es) & falling

        if self.p.regime_filter:
            regime = classify_regime(
                dfs, self.p.tf, adx_trend=self.p.adx_trend, er_trend=self.p.er_trend)
            long_mask = long_mask & (regime == "trend_up")
            short_mask = short_mask & (regime == "trend_down")

        return long_mask.fillna(False), short_mask.fillna(False), atr_val

    # ── vectorized path ────────────────────────────────────────────────────
    def generate_signals(self, dfs: dict) -> pd.DataFrame:
        bars = dfs[self.p.tf]
        long_mask, short_mask, atr_val = self._entry(dfs, bars)

        any_mask = long_mask | short_mask
        fresh = any_mask & ~any_mask.shift(1, fill_value=False)
        cand_idx = np.flatnonzero(fresh.values)

        closes = bars["close"].values
        atr_arr = atr_val.values
        long_arr = long_mask.values

        rows = []
        last_i = -10**9
        for i in cand_idx:
            if i - last_i < self.p.cooldown_bars:
                continue
            a = atr_arr[i]
            if not np.isfinite(a) or a <= 0:
                continue
            last_i = i
            entry = closes[i]
            if long_arr[i]:
                rows.append(dict(time=bars.index[i], direction="buy", entry=entry,
                                 sl=entry - self.p.sl_atr_mult * a,
                                 tp=entry + self.FAR_TP, atr=a))
            else:
                rows.append(dict(time=bars.index[i], direction="sell", entry=entry,
                                 sl=entry + self.p.sl_atr_mult * a,
                                 tp=entry - self.FAR_TP, atr=a))

        cols = ["direction", "entry", "sl", "tp", "atr"]
        if not rows:
            return pd.DataFrame(columns=cols)
        return pd.DataFrame(rows).set_index("time")[cols]

    # ── incremental path ───────────────────────────────────────────────────
    def get_signal(self, dfs: dict) -> Optional[Signal]:
        bars = dfs[self.p.tf]
        need = max(self.p.channel_period, self.p.ema_slow, 200) + self.p.atr_period + 5
        if len(bars) < need:
            return None
        current_bar = bars.index[-1]
        if self._last_signal_bar == current_bar:
            return None

        long_mask, short_mask, atr_val = self._entry(dfs, bars)
        is_long, is_short = bool(long_mask.iloc[-1]), bool(short_mask.iloc[-1])
        if not (is_long or is_short):
            return None
        if bool((long_mask | short_mask).iloc[-2]):
            return None
        a = float(atr_val.iloc[-1])
        if not np.isfinite(a) or a <= 0:
            return None

        entry = float(bars["close"].iloc[-1])
        if is_long:
            sig = Signal("buy", entry, entry - self.p.sl_atr_mult * a,
                         entry + self.FAR_TP, a, current_bar)
        else:
            sig = Signal("sell", entry, entry + self.p.sl_atr_mult * a,
                         entry - self.FAR_TP, a, current_bar)
        self._last_signal_bar = current_bar
        return sig

    def get_indicators(self, dfs: dict) -> dict:
        bars = dfs.get(self.p.tf)
        if bars is None or len(bars) < self.p.channel_period + 5:
            return {}
        result: dict = {
            "atr": round(float(self._atr_series(bars).iloc[-1]), 4),
        }
        if self.p.mode == "donchian":
            result["donchian_high"] = round(float(bars["high"].rolling(self.p.channel_period).max().iloc[-1]), 4)
            result["donchian_low"]  = round(float(bars["low"].rolling(self.p.channel_period).min().iloc[-1]), 4)
        else:
            result["ema_fast"] = round(float(ema(bars["close"], self.p.ema_fast).iloc[-1]), 4)
            result["ema_slow"] = round(float(ema(bars["close"], self.p.ema_slow).iloc[-1]), 4)
        if self.p.regime_filter:
            try:
                result["regime"] = str(classify_regime(
                    dfs, self.p.tf, adx_trend=self.p.adx_trend, er_trend=self.p.er_trend,
                ).iloc[-1])
            except Exception:
                pass
        return result
