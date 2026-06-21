from typing import Optional
from datetime import date
import pandas as pd
from .base import BaseStrategy, Signal
from indicators import atr, ema, adx
from config import LondonBreakoutParams, SharedParams


class LondonBreakoutStrategy(BaseStrategy):
    """
    Asian-range London breakout.
    Tracks the high/low of 00:00–07:00 UTC consolidation on M15.
    Enters when price pushes beyond range ± buffer during London window.
    One trade per day. Optional: trend filter, ADX filter, partial TP.
    """

    def __init__(self, params: LondonBreakoutParams, shared: SharedParams):
        self.p = params
        self.shared = shared
        self._today_traded: Optional[date] = None

    def _add_h1_indicators(self, h1: pd.DataFrame) -> None:
        h1["atr_val"] = atr(h1["high"], h1["low"], h1["close"], self.p.atr_period)
        if self.p.adx_min > 0:
            h1["adx_val"] = adx(h1["high"], h1["low"], h1["close"], 14)
        if self.p.trend_filter:
            h1["ema_trend"] = ema(h1["close"], 50)
            h1["bullish"]   = h1["close"] > h1["ema_trend"]

    # ── Vectorized path (backtest) ────────────────────────────────────────
    def generate_signals(self, dfs: dict) -> pd.DataFrame:
        """
        Pre-compute one signal per trading day.
        Returns DataFrame indexed by M15 bar time with columns:
        direction, entry, sl, tp, atr, partial_tp (NaN if disabled).
        """
        m15 = dfs["M15"]
        h1  = dfs["H1"].copy()
        self._add_h1_indicators(h1)

        # Reindex H1 indicators onto M15 index (no look-ahead ffill)
        atr_m15 = h1["atr_val"].reindex(m15.index, method="ffill")
        if self.p.trend_filter:
            bullish_h1 = h1["bullish"].reindex(m15.index, method="ffill").fillna(True)
        if self.p.adx_min > 0:
            adx_m15 = h1["adx_val"].reindex(m15.index, method="ffill")

        rows = []
        for day, day_bars in m15.groupby(m15.index.date):
            asian = day_bars[
                (day_bars.index.hour >= self.p.asian_start_hour)
                & (day_bars.index.hour < self.p.asian_end_hour)
            ]
            if len(asian) < 4:
                continue

            range_high   = asian["high"].max()
            range_low    = asian["low"].min()
            range_height = range_high - range_low

            london = day_bars[
                (day_bars.index.hour >= self.p.asian_end_hour)
                & (day_bars.index.hour < self.p.london_end_hour)
            ]
            if len(london) == 0:
                continue

            first_london_bar = london.index[0]
            atr_val = atr_m15.get(first_london_bar, 0)
            if atr_val == 0 or pd.isna(atr_val):
                continue

            # Range quality filter
            if range_height > self.p.range_max_atr_mult * atr_val:
                continue
            if range_height < self.p.range_min_atr_mult * atr_val:
                continue

            # ADX filter: skip low-momentum days
            if self.p.adx_min > 0:
                adx_val = adx_m15.get(first_london_bar, 0)
                if pd.isna(adx_val) or adx_val < self.p.adx_min:
                    continue

            buffer = self.p.entry_buffer_atr_mult * atr_val

            for bar_time, bar in london.iterrows():
                direction = None
                entry = sl = tp = None

                if bar["close"] > range_high + buffer:
                    direction = "buy"
                    entry = range_high + buffer
                    sl    = range_low
                    tp    = entry + self.p.tp_range_mult * range_height
                elif bar["close"] < range_low - buffer:
                    direction = "sell"
                    entry = range_low - buffer
                    sl    = range_high
                    tp    = entry - self.p.tp_range_mult * range_height

                if direction is None:
                    continue

                # Trend filter: skip if direction opposes H4/H1 trend
                if self.p.trend_filter:
                    is_bullish = bullish_h1.get(bar_time, True)
                    if direction == "buy"  and not is_bullish:
                        break
                    if direction == "sell" and is_bullish:
                        break

                # Partial TP level
                risk = abs(entry - sl)
                partial_tp_price = float("nan")
                if self.p.partial_tp_enabled:
                    partial_tp_price = (
                        entry + self.p.partial_tp_r * risk
                        if direction == "buy"
                        else entry - self.p.partial_tp_r * risk
                    )

                rows.append(dict(
                    time=bar_time, direction=direction,
                    entry=entry, sl=sl, tp=tp, atr=atr_val,
                    partial_tp=partial_tp_price,
                ))
                break  # one signal per day

        cols = ["direction", "entry", "sl", "tp", "atr", "partial_tp"]
        # full_close_at_partial is read directly from strategy.p in the engine
        if not rows:
            return pd.DataFrame(columns=cols)
        return pd.DataFrame(rows).set_index("time")[cols]

    # ── Incremental path (live bot) ───────────────────────────────────────
    def get_signal(self, dfs: dict) -> Optional[Signal]:
        m15 = dfs["M15"]
        h1  = dfs["H1"].copy()

        if len(m15) < 50 or len(h1) < self.p.atr_period + 10:
            return None

        current_bar  = m15.index[-1]
        today        = current_bar.date()
        current_hour = current_bar.hour

        if current_hour < self.p.asian_end_hour or current_hour >= self.p.london_end_hour:
            return None
        if self._today_traded == today:
            return None

        asian = m15[
            (m15.index.date == today)
            & (m15.index.hour >= self.p.asian_start_hour)
            & (m15.index.hour < self.p.asian_end_hour)
        ]
        if len(asian) < 4:
            return None

        range_high   = asian["high"].max()
        range_low    = asian["low"].min()
        range_height = range_high - range_low

        self._add_h1_indicators(h1)
        atr_val = float(h1["atr_val"].iloc[-1])
        if pd.isna(atr_val) or atr_val == 0:
            return None

        if range_height > self.p.range_max_atr_mult * atr_val:
            return None
        if range_height < self.p.range_min_atr_mult * atr_val:
            return None

        if self.p.adx_min > 0 and float(h1["adx_val"].iloc[-1]) < self.p.adx_min:
            return None

        if self.p.trend_filter:
            bullish = float(h1["close"].iloc[-1]) > float(h1["ema_trend"].iloc[-1])
        else:
            bullish = None  # no filter

        buffer        = self.p.entry_buffer_atr_mult * atr_val
        current_price = m15.iloc[-1]["close"]
        signal        = None

        if current_price > range_high + buffer:
            if bullish is None or bullish:
                entry = range_high + buffer
                signal = Signal("buy", entry, range_low,
                                entry + self.p.tp_range_mult * range_height,
                                atr_val, current_bar)
        elif current_price < range_low - buffer:
            if bullish is None or not bullish:
                entry = range_low - buffer
                signal = Signal("sell", entry, range_high,
                                entry - self.p.tp_range_mult * range_height,
                                atr_val, current_bar)

        if signal:
            self._today_traded = today
        return signal

    def get_indicators(self, dfs: dict) -> dict:
        m15 = dfs.get("M15")
        h1 = dfs.get("H1")
        if m15 is None or h1 is None or len(h1) < self.p.atr_period:
            return {}
        h1 = h1.copy()
        self._add_h1_indicators(h1)
        result: dict = {"atr": round(float(h1["atr_val"].iloc[-1]), 4)}
        today = m15.index[-1].date()
        asian = m15[
            (m15.index.date == today)
            & (m15.index.hour >= self.p.asian_start_hour)
            & (m15.index.hour < self.p.asian_end_hour)
        ]
        if len(asian) >= 1:
            result["range_high"] = round(float(asian["high"].max()), 4)
            result["range_low"]  = round(float(asian["low"].min()), 4)
        if self.p.adx_min > 0:
            result["adx"] = round(float(h1["adx_val"].iloc[-1]), 2)
        if self.p.trend_filter:
            result["ema_trend"] = round(float(h1["ema_trend"].iloc[-1]), 4)
        return result
