from typing import Optional
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from .base import BaseStrategy, Signal
from config import MLClassifierParams, SharedParams
from backtest.ml_features import build_features, build_labels, FEATURE_COLS
from indicators import atr as compute_atr


class MLClassifierStrategy(BaseStrategy):
    """
    Gradient-boosted classifier predicting "TP touched before SL within
    horizon_bars". One model per direction; a trade is signalled only when
    predicted probability >= threshold (high-precision regime).

    fit() must be called with TRAINING data only, before any backtest.
    Labels look forward and are used exclusively inside fit().
    """

    def __init__(self, params: MLClassifierParams, shared: SharedParams):
        self.p = params
        self.shared = shared
        self.exec_tf = params.tf
        self.models = {}            # direction -> fitted classifier
        self._last_signal_bar: Optional[pd.Timestamp] = None

    def _make_model(self) -> HistGradientBoostingClassifier:
        return HistGradientBoostingClassifier(
            max_depth=self.p.max_depth,
            learning_rate=self.p.learning_rate,
            max_iter=self.p.max_iter,
            min_samples_leaf=self.p.min_samples_leaf,
            l2_regularization=self.p.l2_regularization,
            early_stopping=True,
            validation_fraction=0.15,
            random_state=42,
        )

    def fit(self, dfs_train: dict) -> "MLClassifierStrategy":
        bars = dfs_train[self.p.tf]
        X = build_features(dfs_train, self.p.tf)
        # Drop warmup NaNs and the label-horizon tail (labels undefined there)
        valid = X.notna().all(axis=1)
        valid.iloc[-self.p.horizon_bars:] = False

        for direction in ("buy", "sell"):
            y = build_labels(bars, direction, self.p.tp_pts, self.p.sl_pts,
                             self.p.horizon_bars)
            model = self._make_model()
            model.fit(X.loc[valid, FEATURE_COLS], y.loc[valid])
            self.models[direction] = model
        return self

    def _probas(self, dfs: dict) -> pd.DataFrame:
        if not self.models:
            raise RuntimeError("MLClassifierStrategy.fit() must be called first")
        X = build_features(dfs, self.p.tf)
        valid = X.notna().all(axis=1)
        out = pd.DataFrame(index=X.index, data={"buy": 0.0, "sell": 0.0})
        if valid.any():
            Xv = X.loc[valid, FEATURE_COLS]
            for direction, model in self.models.items():
                out.loc[valid, direction] = model.predict_proba(Xv)[:, 1]
        return out

    def _atr_series(self, dfs: dict, bars: pd.DataFrame) -> Optional[pd.Series]:
        h1 = dfs.get("H1")
        if h1 is None:
            return None
        a = compute_atr(h1["high"], h1["low"], h1["close"], 14)
        return a.reindex(bars.index, method="ffill")

    def generate_signals(self, dfs: dict) -> pd.DataFrame:
        bars = dfs[self.p.tf]
        probas = self._probas(dfs)

        buy_mask = probas["buy"] >= self.p.threshold
        sell_mask = (probas["sell"] >= self.p.threshold) & ~buy_mask
        any_mask = buy_mask | sell_mask
        fresh = any_mask & ~any_mask.shift(1, fill_value=False)
        cand_idx = np.flatnonzero(fresh.values)

        closes = bars["close"].values
        buy_arr = buy_mask.values
        atr_s = self._atr_series(dfs, bars) if self.p.manage_trail else None

        rows = []
        last_i = -10**9
        for i in cand_idx:
            if i - last_i < self.p.cooldown_bars:
                continue
            last_i = i
            entry = closes[i]
            atr_val = float(atr_s.iloc[i]) if (atr_s is not None and not pd.isna(atr_s.iloc[i])) else 0.0
            if buy_arr[i]:
                sl, tp, direction = entry - self.p.sl_pts, entry + self.p.tp_pts, "buy"
            else:
                sl, tp, direction = entry + self.p.sl_pts, entry - self.p.tp_pts, "sell"
            rows.append(dict(
                time=bars.index[i], direction=direction,
                entry=entry, sl=sl, tp=tp, atr=atr_val,
            ))

        cols = ["direction", "entry", "sl", "tp", "atr"]
        if not rows:
            return pd.DataFrame(columns=cols)
        return pd.DataFrame(rows).set_index("time")[cols]

    def get_signal(self, dfs: dict) -> Optional[Signal]:
        bars = dfs[self.p.tf]
        if len(bars) < 100:
            return None
        current_bar = bars.index[-1]
        if self._last_signal_bar == current_bar:
            return None

        probas = self._probas(dfs)
        p_buy, p_sell = probas["buy"].iloc[-1], probas["sell"].iloc[-1]
        entry = float(bars["close"].iloc[-1])

        atr_val = 0.0
        if self.p.manage_trail:
            atr_s = self._atr_series(dfs, bars)
            if atr_s is not None:
                v = float(atr_s.iloc[-1])
                if not pd.isna(v):
                    atr_val = v

        signal = None
        if p_buy >= self.p.threshold:
            signal = Signal("buy", entry, entry - self.p.sl_pts,
                            entry + self.p.tp_pts, atr_val, current_bar)
        elif p_sell >= self.p.threshold:
            signal = Signal("sell", entry, entry + self.p.sl_pts,
                            entry - self.p.tp_pts, atr_val, current_bar)

        if signal:
            self._last_signal_bar = current_bar
        return signal

    def get_indicators(self, dfs: dict) -> dict:
        if not self.models:
            return {}
        try:
            probas = self._probas(dfs)
            return {
                "p_buy":  round(float(probas["buy"].iloc[-1]), 4),
                "p_sell": round(float(probas["sell"].iloc[-1]), 4),
            }
        except Exception:
            return {}
