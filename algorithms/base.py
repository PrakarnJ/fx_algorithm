from dataclasses import dataclass
from typing import Optional
import pandas as pd


@dataclass
class Signal:
    direction: str        # 'buy' or 'sell'
    entry_price: float
    sl: float
    tp: float
    atr: float
    bar_time: pd.Timestamp

    def __post_init__(self):
        if self.direction not in ("buy", "sell"):
            raise ValueError(f"Signal direction must be 'buy' or 'sell', got {self.direction!r}")
        if self.direction == "buy":
            if self.sl >= self.entry_price:
                raise ValueError(f"Buy signal: sl {self.sl} must be below entry {self.entry_price}")
            if self.tp <= self.entry_price:
                raise ValueError(f"Buy signal: tp {self.tp} must be above entry {self.entry_price}")
        else:
            if self.sl <= self.entry_price:
                raise ValueError(f"Sell signal: sl {self.sl} must be above entry {self.entry_price}")
            if self.tp >= self.entry_price:
                raise ValueError(f"Sell signal: tp {self.tp} must be below entry {self.entry_price}")


class BaseStrategy:
    def get_signal(self, dfs: dict) -> Optional[Signal]:
        raise NotImplementedError

    def get_indicators(self, dfs: dict) -> dict:
        """Return current indicator values for replay UI. Override in each strategy."""
        return {}
