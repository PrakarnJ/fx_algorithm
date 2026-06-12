from dataclasses import dataclass

SYMBOL = "XAUUSD"
MAGIC = 20240101

# MT5 timeframe integer codes
TF_M15 = 15
TF_H1 = 16385
TF_H4 = 16388

# Winner from iterate.py — all 4 enhancements kept
ACTIVE_STRATEGY = "breakout"


@dataclass
class SharedParams:
    risk_pct: float = 0.01           # 1% of balance risked per trade
    max_spread_points: int = 50      # skip entry if spread exceeds this
    max_consec_losses: int = 3       # pause after this many consecutive losses
    consec_loss_pause_hours: int = 24
    daily_loss_stop_pct: float = 0.04  # halt if day loss exceeds 4% of balance
    breakeven_atr_mult: float = 1.0          # move SL to BE when profit >= 1x ATR
    trail_atr_mult: float = 1.5              # trail SL at 1.5x ATR behind price
    trail_after_partial_atr_mult: float = 0.75  # tighter trail on remainder after partial TP


@dataclass
class TrendFollowingParams:
    ema_fast: int = 9
    ema_slow: int = 21
    ema_trend: int = 50   # H4 trend EMA
    rsi_period: int = 14
    atr_period: int = 14
    sl_atr_mult: float = 1.5
    tp_atr_mult: float = 3.0


@dataclass
class LondonBreakoutParams:
    asian_start_hour: int = 0    # UTC
    asian_end_hour: int = 7      # UTC
    london_end_hour: int = 11    # UTC — cancel unfilled orders after this
    entry_buffer_atr_mult: float = 0.1
    range_max_atr_mult: float = 1.5  # skip if Asian range > 1.5x ATR
    range_min_atr_mult: float = 0.3  # skip if Asian range < 0.3x ATR
    tp_range_mult: float = 2.0       # TP = entry + 2x range height
    atr_period: int = 14
    # Win-rate boosters (off by default; enabled during iteration)
    partial_tp_enabled: bool = False  # close 50% at partial_tp_r × risk, move SL to BE
    partial_tp_r: float = 1.0         # partial TP at 1R from entry
    trend_filter: bool = False        # only trade in H4 EMA(50) direction
    adx_min: float = 0.0              # skip day if H1 ADX(14) < this; 0 = disabled
    time_stop_hours: int = 0          # close if open > N H1 bars; 0 = disabled
    full_close_at_partial: bool = False  # close 100% at partial level (scalp mode — no runner)


SHARED = SharedParams()
TREND_PARAMS = TrendFollowingParams()
# Final winning configuration — all 4 enhancements from iterate.py
BREAKOUT_PARAMS = LondonBreakoutParams(
    london_end_hour=11,
    tp_range_mult=3.0,
    range_max_atr_mult=2.0,
    range_min_atr_mult=0.2,
    partial_tp_enabled=True,
    partial_tp_r=1.0,
    trend_filter=True,
    adx_min=20.0,
    time_stop_hours=8,
)
