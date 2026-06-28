from typing import Optional
import numpy as np
import pandas as pd
from .base import BaseStrategy, Signal
from indicators import ema, rsi, atr
from config import TrendFollowingParams, SharedParams


class TrendFollowingStrategy(BaseStrategy):
    """
    Multi-timeframe EMA crossover + RSI momentum filter.
    H4 EMA(50) sets bias; H1 EMA(9/21) crossover triggers entry;
    RSI(14) confirms momentum is not exhausted.
    """

    def __init__(self, params: TrendFollowingParams, shared: SharedParams):
        self.p = params
        self.shared = shared
        self._last_signal_bar: Optional[pd.Timestamp] = None

    def _add_indicators(self, h1: pd.DataFrame, h4: "pd.DataFrame | None") -> None:
        h1["ema_fast"] = ema(h1["close"], self.p.ema_fast)
        h1["ema_slow"] = ema(h1["close"], self.p.ema_slow)
        h1["rsi"]      = rsi(h1["close"], self.p.rsi_period)
        h1["atr"]      = atr(h1["high"], h1["low"], h1["close"], self.p.atr_period)
        if h4 is not None:
            h4["ema_trend"] = ema(h4["close"], self.p.ema_trend)

    def generate_signals(self, dfs: dict) -> pd.DataFrame:
        """
        Pre-compute all signals at once (vectorized).
        Returns DataFrame indexed by H1 bar time with columns:
        direction, entry, sl, tp, atr. Empty rows = no signal.
        """
        h1 = dfs["H1"].copy()
        h4 = dfs["H4"].copy()

        self._add_indicators(h1, h4)

        # Forward-fill H4 values into H1 index (no look-ahead)
        h4_close_h1 = h4["close"].reindex(h1.index, method="ffill")
        h4_trend_h1 = h4["ema_trend"].reindex(h1.index, method="ffill")
        bullish_h4 = h4_close_h1 > h4_trend_h1

        prev_fast = h1["ema_fast"].shift(1)
        prev_slow = h1["ema_slow"].shift(1)
        crossed_up   = (prev_fast <= prev_slow) & (h1["ema_fast"] > h1["ema_slow"])
        crossed_down = (prev_fast >= prev_slow) & (h1["ema_fast"] < h1["ema_slow"])

        rsi_buy  = (h1["rsi"] >= 50) & (h1["rsi"] <= 70)
        rsi_sell = (h1["rsi"] >= 30) & (h1["rsi"] <= 50)
        session  = (h1.index.hour >= 7) & (h1.index.hour < 22)
        median_atr = h1["atr"].median()
        vol_ok   = h1["atr"] >= 0.3 * median_atr

        buy_mask  = crossed_up   & bullish_h4  & rsi_buy  & session & vol_ok
        sell_mask = crossed_down & ~bullish_h4 & rsi_sell & session & vol_ok

        out = pd.DataFrame(index=h1.index[buy_mask | sell_mask])
        out["direction"] = np.where(
            buy_mask[buy_mask | sell_mask], "buy", "sell"
        )
        out["entry"] = h1.loc[buy_mask | sell_mask, "close"].values
        out["atr"]   = h1.loc[buy_mask | sell_mask, "atr"].values

        sl_vals = np.where(
            out["direction"] == "buy",
            out["entry"] - self.p.sl_atr_mult * out["atr"],
            out["entry"] + self.p.sl_atr_mult * out["atr"],
        )
        tp_vals = np.where(
            out["direction"] == "buy",
            out["entry"] + self.p.tp_atr_mult * out["atr"],
            out["entry"] - self.p.tp_atr_mult * out["atr"],
        )
        out["sl"] = sl_vals
        out["tp"] = tp_vals

        # Partial TP: close 50% at partial_tp_r × initial risk, trail runner
        risk = np.abs(out["entry"].values - out["sl"].values)
        partial_tp_vals = np.where(
            out["direction"] == "buy",
            out["entry"].values + self.p.partial_tp_r * risk,
            out["entry"].values - self.p.partial_tp_r * risk,
        ) if self.p.partial_tp_enabled else float("nan")
        out["partial_tp"] = partial_tp_vals
        return out

    def get_signal(self, dfs: dict) -> Optional[Signal]:
        h1 = dfs["H1"].copy()
        h4 = dfs["H4"].copy()

        if len(h1) < self.p.ema_slow + 10 or len(h4) < self.p.ema_trend + 10:
            return None

        self._add_indicators(h1, h4)

        current_bar = h1.index[-1]

        # Session filter: London + New York only (07:00–22:00 UTC)
        if current_bar.hour < 7 or current_bar.hour >= 22:
            return None

        # One signal per bar
        if self._last_signal_bar == current_bar:
            return None

        prev, curr = h1.iloc[-2], h1.iloc[-1]
        h4_last = h4.iloc[-1]

        atr_val = curr["atr"]
        if pd.isna(atr_val) or atr_val == 0:
            return None

        # Volatility floor: skip dead-market conditions
        median_atr = h1["atr"].median()
        if atr_val < 0.3 * median_atr:
            return None

        bullish_trend = h4_last["close"] > h4_last["ema_trend"]
        crossed_up = prev["ema_fast"] <= prev["ema_slow"] and curr["ema_fast"] > curr["ema_slow"]
        crossed_down = prev["ema_fast"] >= prev["ema_slow"] and curr["ema_fast"] < curr["ema_slow"]

        rsi_val = curr["rsi"]
        entry = curr["close"]
        signal = None

        if crossed_up and bullish_trend and 50 <= rsi_val <= 70:
            sl = entry - self.p.sl_atr_mult * atr_val
            tp = entry + self.p.tp_atr_mult * atr_val
            risk = entry - sl
            partial_tp = (entry + self.p.partial_tp_r * risk) if self.p.partial_tp_enabled else None
            signal = Signal("buy", entry, sl, tp, atr_val, current_bar, partial_tp=partial_tp)

        elif crossed_down and not bullish_trend and 30 <= rsi_val <= 50:
            sl = entry + self.p.sl_atr_mult * atr_val
            tp = entry - self.p.tp_atr_mult * atr_val
            risk = sl - entry
            partial_tp = (entry - self.p.partial_tp_r * risk) if self.p.partial_tp_enabled else None
            signal = Signal("sell", entry, sl, tp, atr_val, current_bar, partial_tp=partial_tp)

        if signal:
            self._last_signal_bar = current_bar
        return signal

    def get_indicators(self, dfs: dict) -> dict:
        h1 = dfs.get("H1")
        h4 = dfs.get("H4")
        if h1 is None or len(h1) < self.p.ema_slow:
            return {}
        h1 = h1.copy()
        h4 = h4.copy() if h4 is not None else None
        self._add_indicators(h1, h4)
        result = {
            "ema_fast": round(float(h1["ema_fast"].iloc[-1]), 4),
            "ema_slow": round(float(h1["ema_slow"].iloc[-1]), 4),
            "rsi":      round(float(h1["rsi"].iloc[-1]), 2),
            "atr":      round(float(h1["atr"].iloc[-1]), 4),
        }
        if h4 is not None and len(h4) >= self.p.ema_trend:
            trend = float(h4["ema_trend"].iloc[-1])
            result["ema_trend_h4"] = round(trend, 4)
            result["h4_bullish"] = int(float(h4["close"].iloc[-1]) > trend)
        return result
