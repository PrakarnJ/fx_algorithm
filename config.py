from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).parent
STOCKS_DIR = ROOT_DIR / "stocks"
LOGS_DIR = ROOT_DIR / "logs"
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"

SYMBOL = "XAUUSD"
MAGIC = 20240101

# MT5 timeframe integer codes
TF_M15 = 15
TF_H1 = 16385
TF_H4 = 16388

# Strategy in use by the live bot: "trend" | "breakout" | "regime_switch".
# regime_switch is the walk-forward winner on REAL data (PF 1.77 OOS).
# ⚠ DEMO ONLY — never forward-tested; profit was tail-driven. See DEPLOYMENT.md.
ACTIVE_STRATEGY = "regime_switch"


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
    # Transaction costs (price points; 1 pt = 0.01 in price = $1/lot on XAUUSD)
    commission_pts: float = 0.0      # round-trip commission per trade
    swap_pts_per_night: float = 0.0  # overnight rollover cost per calendar night held
    slippage_pts: float = 0.0        # extra fill slippage when SL is hit


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


@dataclass
class MeanReversionParams:
    tf: str = "M15"                # signal/execution timeframe
    z_lookback: int = 60           # rolling window for z-score
    z_entry: float = 2.0           # |z| threshold to fade
    rsi_confirm: bool = False      # require RSI extreme as confirmation
    rsi_period: int = 3
    rsi_extreme: float = 20.0      # buy if RSI < x, sell if RSI > 100-x
    tp_pts: float = 3.0            # fixed take-profit in price points
    sl_pts: float = 9.0            # fixed stop-loss in price points
    cooldown_bars: int = 16        # min exec bars between signals
    time_stop_hours: int = 6       # 0 = disabled
    session_start: int = 0         # UTC hour gate (0/24 = always on)
    session_end: int = 24
    manage_trail: bool = False     # False = fixed SL/TP only (scalp mode)


@dataclass
class RsiFadeParams:
    tf: str = "M15"
    rsi_period: int = 2
    buy_below: float = 10.0
    sell_above: float = 90.0
    trend_gate: bool = False       # only fade against H1 EMA(50) extension
    tp_pts: float = 3.0
    sl_pts: float = 9.0
    cooldown_bars: int = 16
    time_stop_hours: int = 6
    session_start: int = 0
    session_end: int = 24
    manage_trail: bool = False


@dataclass
class MLClassifierParams:
    tf: str = "M15"
    tp_pts: float = 3.0            # label + trade target
    sl_pts: float = 9.0
    horizon_bars: int = 32         # label horizon (exec bars)
    threshold: float = 0.85        # min predicted probability to trade
    cooldown_bars: int = 16
    time_stop_hours: int = 8
    manage_trail: bool = False
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
    atr_period: int = 14
    cooldown_bars: int = 8
    # range leg
    range_enabled: bool = True      # mean-revert in ranges; False = stand aside
    z_lookback: int = 60
    z_entry: float = 2.0
    range_tp_pts: float = 4.0
    range_sl_pts: float = 10.0


SHARED = SharedParams()
TREND_PARAMS = TrendFollowingParams()
# Regime-aware switch — params optimized on the most recent 12 months
# (2025-06 → 2026-06), i.e. what walk-forward would carry into "now".
# Re-derive periodically: see backtest/walkforward.py. range_enabled=False
# means it rides trends only and stands aside in ranges (recent regime favored this).
REGIME_PARAMS = RegimeSwitchParams(
    tf="H4", adx_trend=20.0, er_trend=0.4, ema_slow=120, channel_period=80,
    trend_sl_atr_mult=3.5, trend_breakeven_atr_mult=1.0, trend_trail_atr_mult=2.0,
    atr_period=14, cooldown_bars=14, range_enabled=False,
    z_lookback=90, z_entry=1.5, range_tp_pts=4.0, range_sl_pts=6.0,
)

# Live override: the re-optimize pipeline / dashboard "Apply" writes the latest
# approved params here. If present, it supersedes the defaults above — so the
# bot picks up re-optimized params without editing source. Delete to revert.
import json as _json, os as _os
_REGIME_OVERRIDE = _os.path.join(_os.path.dirname(__file__), "data", "regime_params.json")
if _os.path.exists(_REGIME_OVERRIDE):
    try:
        REGIME_PARAMS = RegimeSwitchParams(**_json.load(open(_REGIME_OVERRIDE)))
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
