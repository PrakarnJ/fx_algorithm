"""Load and query the stocks registry.yaml."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict

import yaml

_REGISTRY_PATH = Path(__file__).parent / "registry.yaml"


@lru_cache(maxsize=1)
def load_registry() -> Dict[str, dict]:
    with open(_REGISTRY_PATH) as f:
        return yaml.safe_load(f) or {}


def list_symbols() -> list[str]:
    return list(load_registry().keys())


def get_symbol_meta(symbol: str) -> dict:
    return load_registry().get(symbol, {})


def get_symbol_spread(symbol: str) -> int:
    return get_symbol_meta(symbol).get("spread_points", 20)


def get_yf_ticker(symbol: str) -> str:
    return get_symbol_meta(symbol).get("yfinance_ticker", symbol)
