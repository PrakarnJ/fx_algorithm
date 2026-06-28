from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).parent
STOCKS_DIR = ROOT_DIR / "stocks"
LOGS_DIR = ROOT_DIR / "logs"
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"

SYMBOL = "XAUUSD"

# Active strategy for backtest and dashboard: "trend_following" | "london_breakout" | "regime_switch".
# trend_following is the OOS winner on REAL Dukascopy data (compare.py 2026-06-27):
#   ema_fast=11, ema_slow=34, sl=2.5×ATR, tp=3.5×ATR → OOS PF 1.462, expectancy +11.0 pts, 41 trades 2025+.
ACTIVE_STRATEGY = "regime_switch"


@dataclass
class SharedParams:
    risk_pct: float = 0.50           # 50% of balance risked per trade
    max_spread_points: int = 50      # skip entry if spread exceeds this
    max_consec_losses: int = 3       # pause after this many consecutive losses
    consec_loss_pause_hours: int = 24
    daily_loss_stop_pct: float = 0.04  # halt if day loss exceeds 4% of balance
    breakeven_atr_mult: float = 1.0          # move SL to BE when profit >= 1x ATR
    trail_atr_mult: float = 1.5              # trail SL at 1.5x ATR behind price
    trail_after_partial_atr_mult: float = 0.75  # tighter trail on remainder after partial TP
    # Transaction costs (price points; 1 pt = 0.01 in price = $1/lot on XAUUSD)
    commission_pts: float = 0.0      # round-trip commission per trade
    swap_pts_per_night: float = 0.0  # overnight rollover cost per calendar night held
    slippage_pts: float = 0.0        # extra fill slippage when SL is hit


@dataclass
class TrendFollowingParams:
    # IS-optimized 2026-06-27 on real Dukascopy XAUUSD 2022-2024, validated OOS 2025+:
    # PF 1.462, expectancy +11.0 pts, 41 OOS trades — compare.py winner.
    ema_fast: int = 11
    ema_slow: int = 34
    ema_trend: int = 50   # H4 trend EMA
    rsi_period: int = 14
    atr_period: int = 14
    sl_atr_mult: float = 2.5
    tp_atr_mult: float = 3.5
    partial_tp_enabled: bool = True   # close 50% early to lock in profit
    partial_tp_r: float = 1.5         # partial TP at 1.5× risk from entry
    # trailing — wide so trends breathe (overrides SharedParams in engine)
    breakeven_atr_mult: float = 2.0   # move SL to BE after 2× ATR in profit
    trail_atr_mult: float = 3.0       # trail at 3× ATR behind price


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


@dataclass
class MeanReversionParams:
    tf: str = "M15"                # signal/execution timeframe
    z_lookback: int = 60           # rolling window for z-score
    z_entry: float = 2.0           # |z| threshold to fade
    rsi_confirm: bool = False      # require RSI extreme as confirmation
    rsi_period: int = 3
    rsi_extreme: float = 20.0      # buy if RSI < x, sell if RSI > 100-x
    sl_atr_mult: float = 0.8       # SL at 0.8× ATR from entry (adaptive)
    tp_atr_mult: float = 2.0       # TP at 2.0× ATR → R:R = 2.5:1
    cooldown_bars: int = 16        # min exec bars between signals
    time_stop_hours: int = 6       # 0 = disabled
    session_start: int = 0         # UTC hour gate (0/24 = always on)
    session_end: int = 24
    manage_trail: bool = True      # trail SL after break-even


@dataclass
class RsiFadeParams:
    tf: str = "M15"
    rsi_period: int = 2
    buy_below: float = 10.0
    sell_above: float = 90.0
    trend_gate: bool = True        # only fade when H1 EMA(50) agrees with direction
    sl_atr_mult: float = 0.8       # SL at 0.8× ATR from entry (adaptive)
    tp_atr_mult: float = 2.0       # TP at 2.0× ATR → R:R = 2.5:1
    cooldown_bars: int = 16
    time_stop_hours: int = 6
    session_start: int = 0
    session_end: int = 24
    manage_trail: bool = True      # trail SL after break-even


@dataclass
class MLClassifierParams:
    tf: str = "M15"
    tp_pts: float = 8.0            # label + trade target — 2.67:1 R:R (was 3.0)
    sl_pts: float = 3.0            # tight cut-loss (was 9.0 — inverted R:R)
    horizon_bars: int = 32         # label horizon (exec bars)
    threshold: float = 0.30        # min predicted probability to trade (model max ~0.35)
    cooldown_bars: int = 16
    time_stop_hours: int = 8
    manage_trail: bool = True      # trail SL after break-even (was False)
    # model hyperparameters (HistGradientBoostingClassifier)
    max_depth: int = 4
    learning_rate: float = 0.08
    max_iter: int = 250
    min_samples_leaf: int = 60
    l2_regularization: float = 1.0


@dataclass
class TrendBreakoutParams:
    tf: str = "H1"                  # signal/execution timeframe
    mode: str = "donchian"          # "donchian" | "ma_momentum"
    channel_period: int = 40        # Donchian lookback (bars)
    ema_fast: int = 20              # ma_momentum fast EMA
    ema_slow: int = 50              # ma_momentum slow EMA
    slope_lookback: int = 10        # bars for EMA-slope confirmation
    sl_atr_mult: float = 2.5        # initial stop distance (wide)
    atr_period: int = 14
    cooldown_bars: int = 8
    # trailing (engine update_sl) — wide so trends can breathe
    breakeven_atr_mult: float = 1.5
    trail_atr_mult: float = 3.0
    regime_filter: bool = True      # only enter in matching trend regime
    adx_trend: float = 25.0
    er_trend: float = 0.30
    partial_tp_enabled: bool = True  # close 50% early; trail the runner
    partial_tp_r: float = 2.0        # partial TP at 2× initial risk


@dataclass
class RegimeSwitchParams:
    tf: str = "H1"
    # regime thresholds
    adx_trend: float = 25.0
    er_trend: float = 0.30
    ema_slow: int = 200
    # trend leg (Donchian)
    channel_period: int = 40
    trend_sl_atr_mult: float = 2.5
    trend_breakeven_atr_mult: float = 1.5
    trend_trail_atr_mult: float = 3.0
    trend_partial_tp_enabled: bool = True  # lock in 50% at 2× risk; trail runner
    trend_partial_tp_r: float = 2.0
    atr_period: int = 14
    cooldown_bars: int = 8
    # range leg
    range_enabled: bool = True      # mean-revert in ranges; False = stand aside
    z_lookback: int = 60
    z_entry: float = 2.0
    range_sl_atr_mult: float = 0.8  # ATR-based SL (was range_sl_pts=10.0)
    range_tp_atr_mult: float = 2.0  # ATR-based TP → R:R = 2.5:1 (was range_tp_pts=4.0)


@dataclass
class MyStrategyParams:
    # Multi-TF trend filter EMAs (Daily via H4 resample, H4, H1)
    ema_fast: int = 34
    ema_slow: int = 89
    # StochRSI on M15
    stochrsi_period: int = 14
    stochrsi_k: int = 3
    stochrsi_d: int = 3
    stochrsi_buy: float = 20.0     # K below this → oversold, confirm buy
    stochrsi_sell: float = 70.0    # K above this → overbought, confirm sell
    # Lookback for StochRSI: pullback (oversold) precedes MACD zero-cross (recovery)
    # by several bars — same-bar conjunction is empirically empty. 8 bars = 2 hours.
    stochrsi_lookback_bars: int = 8
    # MACD on M15
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal_period: int = 9
    # ATR
    atr_period: int = 14
    # SL / TP (ATR-based)
    sl_atr_mult: float = 2.0
    tp_atr_mult: float = 3.5
    # S/R detection (on H4 bars)
    sr_lookback: int = 200         # H4 bars to scan (~33 calendar days)
    sr_min_touches: int = 3        # minimum touches to qualify as S/R level
    sr_tolerance_atr: float = 0.5  # price within 0.5×ATR of S/R level to qualify
    require_sr: bool = True        # disable to trade without S/R filter
    # EMA cross validity window on H1
    cross_lookback_h1: int = 4     # accept cross that happened ≤ N H1 bars ago
    # Stepped SL ("zero risk" mechanic)
    use_stepped_sl: bool = True    # BE at 25% of TP distance; lock 25% profit at 50%


MY_PARAMS = MyStrategyParams()


@dataclass
class PullbackScalperParams:
    ema_trend: int = 50          # H1 EMA for trend direction
    ema_slope_lookback: int = 5  # H1 bars to measure EMA slope
    adx_period: int = 14
    adx_min: float = 20.0        # require trending market
    ema_entry: int = 21          # M15 EMA price must pull back to
    atr_period: int = 14
    ema_touch_atr: float = 0.5   # price within N×ATR of EMA21 to qualify
    rsi_period: int = 14
    rsi_buy_lo: float = 35.0     # RSI floor — not a crash, just a pullback
    rsi_buy_hi: float = 55.0     # RSI ceiling — not already extended
    rsi_sell_lo: float = 45.0
    rsi_sell_hi: float = 65.0
    sl_atr_mult: float = 2.5
    tp_atr_mult: float = 5.0     # 2:1 R:R
    session_start: int = 7       # UTC hour — London open
    session_end: int = 17        # UTC hour — NY close
    cooldown_bars: int = 8       # min M15 bars between signals


PULLBACK_PARAMS = PullbackScalperParams()


@dataclass
class VolatilityBreakoutParams:
    # Trend filter (H1)
    ema_trend: int = 50
    adx_period: int = 14
    adx_min: float = 25.0          # H1 ADX must be trending — cuts fakeouts in ranges
    # Volatility expansion (M15 ATR vs its own rolling average)
    atr_period: int = 14
    atr_avg_period: int = 20       # rolling window for ATR baseline
    atr_expansion: float = 1.3     # ATR must exceed N × rolling average (90th pct)
    # Donchian channel breakout confirmation
    donchian_period: int = 20      # M15 bars; price must close above/below N-bar high/low
    require_new_extreme: bool = True
    # SL / TP
    sl_atr_mult: float = 1.0       # tight — the expansion candle is the edge
    tp_atr_mult: float = 2.5       # 2.5:1 R:R → break-even at 29% WR
    # Session gate (UTC)
    session_start: int = 7
    session_end: int = 17
    cooldown_bars: int = 8


VOLATILITY_BREAKOUT_PARAMS = VolatilityBreakoutParams()

SHARED = SharedParams()
TREND_PARAMS = TrendFollowingParams()
# Regime-aware switch — params optimized on the most recent 12 months
# (2025-06 → 2026-06), i.e. what walk-forward would carry into "now".
# Re-derive periodically: see backtest/walkforward.py. range_enabled=False
# means it rides trends only and stands aside in ranges (recent regime favored this).
REGIME_PARAMS = RegimeSwitchParams(
    tf="H4", adx_trend=20.0, er_trend=0.4, ema_slow=120, channel_period=80,
    trend_sl_atr_mult=3.5, trend_breakeven_atr_mult=1.0, trend_trail_atr_mult=2.0,
    trend_partial_tp_enabled=True, trend_partial_tp_r=2.0,
    atr_period=14, cooldown_bars=14, range_enabled=False,
    z_lookback=90, z_entry=1.5, range_sl_atr_mult=0.8, range_tp_atr_mult=2.0,
)

# Re-optimize override: backtest/reoptimize.py and the dashboard "Apply" button
# write the latest approved params here. If present, supersedes the defaults above.
# Delete to revert.
import json as _json, os as _os
_REGIME_OVERRIDE = _os.path.join(_os.path.dirname(__file__), "data", "regime_params.json")
if _os.path.exists(_REGIME_OVERRIDE):
    try:
        _d = _json.load(open(_REGIME_OVERRIDE))
        REGIME_PARAMS = RegimeSwitchParams(**{k: v for k, v in _d.items() if not k.startswith("_")})
    except Exception as _e:
        print(f"[config] ignoring bad regime_params.json: {_e}")
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
