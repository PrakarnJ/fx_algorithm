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


class BaseStrategy:
    def get_signal(self, dfs: dict) -> Optional[Signal]:
        raise NotImplementedError
