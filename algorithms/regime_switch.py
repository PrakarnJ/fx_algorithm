from typing import Optional
import numpy as np
import pandas as pd
from .base import BaseStrategy, Signal
from .trend_breakout import TrendBreakoutStrategy
from .mean_reversion import MeanReversionStrategy
from indicators import atr
from config import (
    RegimeSwitchParams, SharedParams,
    TrendBreakoutParams, MeanReversionParams,
)
from backtest.regime import classify_regime


class RegimeSwitchStrategy(BaseStrategy):
    """
    Regime-aware composite. Detect trend vs range on the higher timeframe,
    then route:

      - trending  → Donchian trend-follower (rides with the move, ATR trail)
      - ranging   → z-score mean-reversion fade (fixed TP/SL),
                    or stand aside if range_enabled=False

    Trend trades carry a real atr (engine trails them); range trades carry
    atr=0 (engine leaves them on fixed SL/TP). A single SharedParams with a
    wide trail therefore governs trend trades only — see build_regime_switch.
    """

    def __init__(self, params: RegimeSwitchParams, shared: SharedParams):
        self.p = params
        self.shared = shared
        self.exec_tf = params.tf

        self._trend = TrendBreakoutStrategy(TrendBreakoutParams(
            tf=params.tf, mode="donchian", channel_period=params.channel_period,
            sl_atr_mult=params.trend_sl_atr_mult, atr_period=params.atr_period,
            cooldown_bars=params.cooldown_bars,
            breakeven_atr_mult=params.trend_breakeven_atr_mult,
            trail_atr_mult=params.trend_trail_atr_mult,
            regime_filter=True, adx_trend=params.adx_trend, er_trend=params.er_trend,
            partial_tp_enabled=params.trend_partial_tp_enabled,
            partial_tp_r=params.trend_partial_tp_r,
        ), shared)

        self._range = MeanReversionStrategy(MeanReversionParams(
            tf=params.tf, z_lookback=params.z_lookback, z_entry=params.z_entry,
            sl_atr_mult=params.range_sl_atr_mult, tp_atr_mult=params.range_tp_atr_mult,
            cooldown_bars=params.cooldown_bars, manage_trail=True,
        ), shared)
        self._last_signal_bar: Optional[pd.Timestamp] = None

    def _regime(self, dfs: dict) -> pd.Series:
        return classify_regime(
            dfs, self.p.tf, ema_slow=self.p.ema_slow,
            adx_trend=self.p.adx_trend, er_trend=self.p.er_trend)

    def generate_signals(self, dfs: dict) -> pd.DataFrame:
        cols = ["direction", "entry", "sl", "tp", "atr", "partial_tp"]
        regime = self._regime(dfs)

        trend_sig = self._trend.generate_signals(dfs)   # already gated to trends

        frames = [trend_sig]
        if self.p.range_enabled:
            range_sig = self._range.generate_signals(dfs)
            if len(range_sig):
                in_range = regime.reindex(range_sig.index).eq("range")
                frames.append(range_sig[in_range.values])

        merged = pd.concat([f for f in frames if len(f)]) if any(len(f) for f in frames) \
            else pd.DataFrame(columns=cols)
        if len(merged) == 0:
            return pd.DataFrame(columns=cols)
        merged = merged[~merged.index.duplicated(keep="first")].sort_index()
        # Ensure partial_tp column exists (range leg doesn't emit it)
        if "partial_tp" not in merged.columns:
            merged["partial_tp"] = float("nan")
        return merged[cols]

    def get_signal(self, dfs: dict) -> Optional[Signal]:
        bars = dfs[self.p.tf]
        if len(bars) < max(self.p.ema_slow, self.p.channel_period, self.p.z_lookback) + 20:
            return None
        current_bar = bars.index[-1]
        if self._last_signal_bar == current_bar:
            return None

        regime = self._regime(dfs).iloc[-1]
        sig = None
        if regime in ("trend_up", "trend_down"):
            sig = self._trend.get_signal(dfs)
        elif self.p.range_enabled and regime == "range":
            sig = self._range.get_signal(dfs)
        if sig:
            self._last_signal_bar = current_bar
        return sig

    def get_indicators(self, dfs: dict) -> dict:
        bars = dfs.get(self.p.tf)
        if bars is None or len(bars) < self.p.ema_slow + 5:
            return {}
        try:
            regime = str(self._regime(dfs).iloc[-1])
        except Exception:
            regime = "unknown"
        result: dict = {"regime": regime}
        result.update(self._trend.get_indicators(dfs))
        if self.p.range_enabled:
            for k, v in self._range.get_indicators(dfs).items():
                result[f"range_{k}"] = v
        return result
