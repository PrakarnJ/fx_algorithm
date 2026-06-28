from dataclasses import dataclass, field
from typing import Any, List, Optional, Type


# Internal TF key → yfinance interval string (4h is resampled from 1h)
TF_TO_YF = {
    "M1": "1m",
    "M5": "5m",
    "M15": "15m",
    "M30": "30m",
    "H1": "1h",
    "H4": "1h",   # downloaded as 1h, then resampled to 4h
    "D1": "1d",
    "W1": "1wk",
    "MN": "1mo",
}

# CSV filename for each internal TF key (written to stocks/{symbol}/)
TF_TO_FILE = {
    "M1": "1m.csv",
    "M5": "5m.csv",
    "M15": "15m.csv",
    "M30": "30m.csv",
    "H1": "1h.csv",
    "H4": "4h.csv",
    "D1": "1d.csv",
    "W1": "1wk.csv",
    "MN": "1mo.csv",
}


@dataclass
class AlgoManifest:
    name: str
    display_name: str
    strategy_class: Type
    params_class: Type
    default_params: Any
    required_tfs: List[str]      # internal keys needed in dfs dict
    exec_tf: str                  # timeframe the engine runs on
    needs_fit: bool = False
    description: str = ""
    indicator_keys: List[str] = field(default_factory=list)


def _build_registry() -> List[AlgoManifest]:
    from algorithms.trend_following import TrendFollowingStrategy
    from algorithms.london_breakout import LondonBreakoutStrategy
    from algorithms.mean_reversion import MeanReversionStrategy
    from algorithms.rsi_fade import RsiFadeStrategy
    from algorithms.trend_breakout import TrendBreakoutStrategy
    from algorithms.regime_switch import RegimeSwitchStrategy
    from algorithms.ml_classifier import MLClassifierStrategy
    from algorithms.my_strategy import MyStrategy
    from algorithms.pullback_scalper import PullbackScalperStrategy
    from algorithms.volatility_breakout import VolatilityBreakoutStrategy
    from config import (
        TrendFollowingParams, LondonBreakoutParams, MeanReversionParams,
        RsiFadeParams, TrendBreakoutParams, RegimeSwitchParams, MLClassifierParams,
        MyStrategyParams, PullbackScalperParams, VolatilityBreakoutParams,
        TREND_PARAMS, BREAKOUT_PARAMS, REGIME_PARAMS, MY_PARAMS, PULLBACK_PARAMS,
        VOLATILITY_BREAKOUT_PARAMS,
    )

    return [
        AlgoManifest(
            name="trend_following",
            display_name="Trend Following (EMA)",
            strategy_class=TrendFollowingStrategy,
            params_class=TrendFollowingParams,
            default_params=TREND_PARAMS,
            required_tfs=["H1", "H4"],
            exec_tf="H1",
            description="EMA(9/21) crossover on H1 with H4 trend bias and RSI filter.",
            indicator_keys=["ema_fast", "ema_slow", "ema_trend", "rsi", "atr"],
        ),
        AlgoManifest(
            name="london_breakout",
            display_name="London Breakout",
            strategy_class=LondonBreakoutStrategy,
            params_class=LondonBreakoutParams,
            default_params=BREAKOUT_PARAMS,
            required_tfs=["M15", "H1"],   # signals indexed on M15, H1 for filters
            exec_tf="M15",
            description="Asian-session range breakout during London open (07:00–11:00 UTC).",
            indicator_keys=["atr", "range_high", "range_low", "adx"],
        ),
        AlgoManifest(
            name="mean_reversion",
            display_name="Mean Reversion (Z-Score)",
            strategy_class=MeanReversionStrategy,
            params_class=MeanReversionParams,
            default_params=MeanReversionParams(),
            required_tfs=["M15", "H1"],
            exec_tf="M15",
            description="Fade extreme z-score moves on M15 with fixed TP/SL.",
            indicator_keys=["z_score", "mean", "std"],
        ),
        AlgoManifest(
            name="rsi_fade",
            display_name="RSI Fade",
            strategy_class=RsiFadeStrategy,
            params_class=RsiFadeParams,
            default_params=RsiFadeParams(),
            required_tfs=["M15", "H1"],
            exec_tf="M15",
            description="Fade RSI extremes (< 10 buy / > 90 sell) on M15.",
            indicator_keys=["rsi"],
        ),
        AlgoManifest(
            name="trend_breakout",
            display_name="Trend Breakout (Donchian)",
            strategy_class=TrendBreakoutStrategy,
            params_class=TrendBreakoutParams,
            default_params=TrendBreakoutParams(),
            required_tfs=["H1"],
            exec_tf="H1",
            description="Donchian channel breakout with ATR trailing stop and regime filter.",
            indicator_keys=["donchian_high", "donchian_low", "atr", "regime", "adx"],
        ),
        AlgoManifest(
            name="regime_switch",
            display_name="Regime Switch",
            strategy_class=RegimeSwitchStrategy,
            params_class=RegimeSwitchParams,
            default_params=REGIME_PARAMS,
            required_tfs=["H1", "H4"],
            exec_tf=REGIME_PARAMS.tf,
            description="Routes to Donchian trend-follower in trends, z-score fade in ranges.",
            indicator_keys=["regime", "adx", "er", "ema_slow", "atr"],
        ),
        AlgoManifest(
            name="ml_classifier",
            display_name="ML Classifier",
            strategy_class=MLClassifierStrategy,
            params_class=MLClassifierParams,
            default_params=MLClassifierParams(),
            required_tfs=["M15", "H1"],
            exec_tf="M15",
            needs_fit=True,
            description="Gradient-boosted classifier predicting TP-before-SL on M15+H1 features. Auto-trained on the first 70% of bars at backtest time; call MLClassifierStrategy.fit(dfs) manually for live use.",
            indicator_keys=["ml_prob_buy", "ml_prob_sell"],
        ),
        AlgoManifest(
            name="volatility_breakout",
            display_name="Volatility Expansion Breakout",
            strategy_class=VolatilityBreakoutStrategy,
            params_class=VolatilityBreakoutParams,
            default_params=VOLATILITY_BREAKOUT_PARAMS,
            required_tfs=["M15", "H1"],
            exec_tf="M15",
            description=(
                "Enters when M15 ATR spikes above 1.5× its 20-bar average (momentum burst), "
                "in the direction of the H1 EMA(50) trend. 2.5:1 R:R, London+NY session."
            ),
            indicator_keys=["atr_m15", "atr_avg_m15", "atr_ratio", "ema50_h1", "adx_h1"],
        ),
        AlgoManifest(
            name="pullback_scalper",
            display_name="Pullback Scalper (EMA21)",
            strategy_class=PullbackScalperStrategy,
            params_class=PullbackScalperParams,
            default_params=PULLBACK_PARAMS,
            required_tfs=["M15", "H1"],
            exec_tf="M15",
            description=(
                "Enters M15 EMA(21) pullbacks during H1 trends (ADX>20, EMA50 slope). "
                "RSI(14) 35–55 confirms moderate pullback. 2:1 R:R, London+NY session."
            ),
            indicator_keys=["ema21_m15", "ema50_h1", "rsi_m15", "adx_h1", "atr_m15"],
        ),
        AlgoManifest(
            name="my_strategy",
            display_name="My Strategy (MTF Confluence)",
            strategy_class=MyStrategy,
            params_class=MyStrategyParams,
            default_params=MY_PARAMS,
            required_tfs=["M15", "H1", "H4"],
            exec_tf="M15",
            description=(
                "Multi-TF EMA 34/89 trend (Daily+H4+H1) + H1 crossover trigger + "
                "StochRSI oversold/overbought + MACD histogram flip + H4 S/R proximity. "
                "Stepped SL: BE at 25% TP, lock 25% profit at 50% TP."
            ),
            indicator_keys=["ema34_daily", "ema89_daily", "ema34_h4", "ema89_h4",
                            "ema34_h1", "ema89_h1", "stochrsi_k", "stochrsi_d",
                            "macd_hist", "atr_m15"],
        ),
    ]


_REGISTRY: Optional[List[AlgoManifest]] = None


def get_registry() -> List[AlgoManifest]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    return _REGISTRY


def list_algos() -> List[AlgoManifest]:
    return get_registry()


def get_algo(name: str) -> Optional[AlgoManifest]:
    return next((a for a in get_registry() if a.name == name), None)
