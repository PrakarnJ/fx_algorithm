"""Compile + run a Pine script over XAUUSD bars and serialize the result."""
from __future__ import annotations

import math
from typing import Optional

import pandas as pd

from pine import ast_nodes as A
from pine.errors import PineCompileError, PineRuntimeError
from pine.interpreter import Interpreter
from pine.parser import parse
from pine.tester import Broker, TesterSettings

import config


def compile_source(source: str) -> A.Program:
    """Parse and validate; raises PineCompileError with line/col on failure."""
    return parse(source)


def _clean(v: float) -> Optional[float]:
    return None if (isinstance(v, float) and math.isnan(v)) else v


def run(program: A.Program, df: pd.DataFrame,
        settings_overrides: Optional[dict] = None, timeframe: str = "H1") -> dict:
    """Execute a compiled program over UTC-indexed OHLC bars.

    Returns a JSON-ready dict: bars, plots, shapes, hlines, trades, equity,
    metrics (strategy scripts only).
    """
    is_strategy = program.script_type == "strategy"

    broker = None
    if is_strategy:
        s = dict(program.settings)
        if settings_overrides:
            s.update({k: v for k, v in settings_overrides.items() if v is not None})
        settings = TesterSettings(
            initial_capital=float(s.get("initial_capital", config.DEFAULT_INITIAL_CAPITAL)),
            default_qty_type=str(s.get("default_qty_type", config.DEFAULT_QTY_TYPE)),
            default_qty_value=float(s.get("default_qty_value", config.DEFAULT_QTY_VALUE)),
            commission_type=str(s.get("commission_type", config.DEFAULT_COMMISSION_TYPE)),
            commission_value=float(s.get("commission_value", config.DEFAULT_COMMISSION_VALUE)),
            tick_size=config.TICK_SIZE,
            process_orders_on_close=bool(s.get("process_orders_on_close", False)),
        )
        broker = Broker(
            df["open"].to_numpy(dtype=float), df["high"].to_numpy(dtype=float),
            df["low"].to_numpy(dtype=float), df["close"].to_numpy(dtype=float),
            settings)

    interp = Interpreter(program, df, broker, timeframe=timeframe)
    interp.run()

    times = interp.times
    n = interp.n

    bars = [{"time": int(times[i]),
             "open": float(interp.series["open"][i]),
             "high": float(interp.series["high"][i]),
             "low": float(interp.series["low"][i]),
             "close": float(interp.series["close"][i])}
            for i in range(n)]

    plots = []
    for uid, p in interp.collector.plots.items():
        values = p["values"] + [float("nan")] * (n - len(p["values"]))
        plots.append({
            "id": f"plot{uid}",
            "title": p["title"],
            "color": p["color"],
            "style": p["style"],
            "overlay": program.overlay,
            "values": [_clean(v) for v in values],
        })

    result = {
        "ok": True,
        "script_type": program.script_type,
        "title": program.title,
        "errors": [],
        "bars": bars,
        "plots": plots,
        "shapes": interp.collector.shapes,
        "hlines": list(interp.collector.hlines.values()),
        "trades": [],
        "equity": [],
        "metrics": None,
    }

    if broker is not None:
        result["trades"] = [{
            "entry_time": int(times[t.entry_bar]),
            "exit_time": int(times[t.exit_bar]),
            "direction": t.direction,
            "entry_price": round(t.entry_price, 5),
            "exit_price": round(t.exit_price, 5),
            "qty": round(t.qty, 6),
            "profit": round(t.profit, 2),
            "profit_pct": round(t.profit / (t.entry_price * t.qty) * 100.0, 3)
                          if t.entry_price * t.qty else None,
            "entry_id": t.entry_id,
            "exit_reason": t.exit_reason,
        } for t in broker.closed]
        result["equity"] = [round(e, 2) for e in broker.equity_curve]
        result["metrics"] = broker.metrics()

    return result


def load_bars(timeframe: str, start_date: Optional[str] = None,
              end_date: Optional[str] = None) -> pd.DataFrame:
    """Load XAUUSD bars for one timeframe from data/."""
    fname = config.TF_TO_FILE.get(timeframe)
    if fname is None:
        raise ValueError(f"unknown timeframe {timeframe!r} — use one of {list(config.TF_TO_FILE)}")
    path = config.DATA_DIR / fname
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found — generate with data/generate_synthetic.py "
            f"or import real bars with data/convert_dukascopy.py")
    df = pd.read_csv(path, index_col="time", parse_dates=True)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    if start_date:
        df = df[df.index >= pd.Timestamp(start_date, tz="UTC")]
    if end_date:
        df = df[df.index <= pd.Timestamp(end_date, tz="UTC") + pd.Timedelta(days=1)]
    return df
