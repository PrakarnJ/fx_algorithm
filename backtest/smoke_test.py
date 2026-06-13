"""
Pre-campaign smoke tests. All must pass before launching backtest/campaign.py.

1. Shape/sanity:      each new strategy emits well-formed signals.
2. No-look-ahead:     prefix property — signals computed on truncated data
                      equal the full-run signals over the same range.
3. Live parity:       get_signal (incremental) agrees with generate_signals
                      (vectorized) bar-by-bar.
4. exec_tf engine:    H1 default regression + M15 fill/time-stop correctness.

Run: python backtest/smoke_test.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd

from config import (
    SharedParams, BREAKOUT_PARAMS,
    MeanReversionParams, RsiFadeParams, MLClassifierParams,
)
from strategies.london_breakout import LondonBreakoutStrategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.rsi_fade import RsiFadeStrategy
from strategies.ml_classifier import MLClassifierStrategy
from backtest.engine import load_data, run_backtest_fast, Trade

SHARED = SharedParams()
FAILURES = []


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


def signal_sanity(name: str, strategy, dfs: dict) -> pd.DataFrame:
    sig = strategy.generate_signals(dfs)
    check(f"{name}: has signals", len(sig) > 0, "no signals generated")
    if len(sig) == 0:
        return sig
    check(f"{name}: columns", all(c in sig.columns for c in ("direction", "entry", "sl", "tp", "atr")))
    buys = sig[sig["direction"] == "buy"]
    sells = sig[sig["direction"] == "sell"]
    ok_buy = ((buys["sl"] < buys["entry"]) & (buys["entry"] < buys["tp"])).all() if len(buys) else True
    ok_sell = ((sells["tp"] < sells["entry"]) & (sells["entry"] < sells["sl"])).all() if len(sells) else True
    check(f"{name}: SL/TP ordering", bool(ok_buy and ok_sell))
    return sig


def prefix_test(name: str, strategy, dfs: dict, n_cuts: int = 8) -> None:
    full = strategy.generate_signals(dfs)
    if len(full) < 3:
        check(f"{name}: prefix (skipped — too few signals)", True)
        return
    tf = getattr(strategy, "exec_tf", "M15")
    idx = dfs[tf].index
    rng = np.random.default_rng(7)
    cuts = sorted(rng.choice(np.arange(len(idx) // 2, len(idx) - 1), size=n_cuts, replace=False))
    ok = True
    for c in cuts:
        t = idx[c]
        dfs_cut = {k: v[v.index <= t] for k, v in dfs.items()}
        part = strategy.generate_signals(dfs_cut)
        expect = full[full.index <= t]
        if len(part) != len(expect) or not (part.index == expect.index).all():
            ok = False
            break
        if not np.allclose(part[["entry", "sl", "tp"]].values,
                           expect[["entry", "sl", "tp"]].values, atol=1e-9):
            ok = False
            break
    check(f"{name}: no-look-ahead prefix", ok)


def parity_test(name: str, strategy_cls, params, dfs: dict, n_bars: int = 400) -> None:
    """get_signal called incrementally must reproduce generate_signals.
    Uses cooldown_bars=1 so the vectorized cooldown filter is a no-op."""
    from dataclasses import replace
    p = replace(params, cooldown_bars=1)
    tf = p.tf
    vec = strategy_cls(p, SHARED).generate_signals(dfs)

    inc = strategy_cls(p, SHARED)
    bars = dfs[tf]
    start = len(bars) - n_bars
    got = []
    for i in range(start, len(bars) + 1):
        t = bars.index[i - 1]
        dfs_cut = {k: v[v.index <= t] for k, v in dfs.items()}
        s = inc.get_signal(dfs_cut)
        if s:
            got.append((s.bar_time, s.direction, round(s.entry_price, 6)))

    window_start = bars.index[start - 1]
    expect = [
        (t, r["direction"], round(float(r["entry"]), 6))
        for t, r in vec[vec.index >= window_start].iterrows()
    ]
    check(f"{name}: live/backtest parity", got == expect,
          f"incremental={len(got)} vectorized={len(expect)}")


def exec_tf_test(dfs: dict) -> None:
    # Stub strategy: one buy signal at a fixed M15 bar
    m15 = dfs["M15"]
    i0 = 1100
    entry_bar = m15.index[i0]
    entry = float(m15["close"].iloc[i0])

    class Stub:
        exec_tf = "M15"
        class p:
            time_stop_hours = 2
            full_close_at_partial = False
        def generate_signals(self, dfs):
            return pd.DataFrame(
                [dict(direction="buy", entry=entry, sl=entry - 1e9, tp=entry + 1e9, atr=0.0)],
                index=[entry_bar],
            )

    trades = run_backtest_fast(Stub(), SHARED, dfs, spread_points=0, exec_tf="M15")
    check("exec_tf=M15: stub trade filled", len(trades) == 1)
    if trades:
        t = trades[0]
        check("exec_tf=M15: entry bar correct", t.entry_time == entry_bar)
        bars_held = m15.index.get_loc(t.exit_time) - i0
        check("exec_tf=M15: time-stop 2h = 8 M15 bars", bars_held == 8,
              f"held {bars_held} bars")


def main() -> None:
    dfs_full = load_data()
    # Slice: enough for warmup + plenty of signals, fast to iterate
    dfs = {k: v[v.index <= "2023-06-30"] for k, v in dfs_full.items()}

    print("── 1+2+3. Strategy checks ─────────────────────────")
    mr_params = MeanReversionParams(z_lookback=40, z_entry=1.5, tp_pts=3, sl_pts=9)
    mr = MeanReversionStrategy(mr_params, SHARED)
    signal_sanity("mean_reversion", mr, dfs)
    prefix_test("mean_reversion", mr, dfs)
    parity_test("mean_reversion", MeanReversionStrategy, mr_params, dfs)

    rf_params = RsiFadeParams(rsi_period=2, buy_below=15, sell_above=85, tp_pts=3, sl_pts=9)
    rf = RsiFadeStrategy(rf_params, SHARED)
    signal_sanity("rsi_fade", rf, dfs)
    prefix_test("rsi_fade", rf, dfs)
    parity_test("rsi_fade", RsiFadeStrategy, rf_params, dfs)

    ml_params = MLClassifierParams(threshold=0.6, max_iter=60, horizon_bars=16)
    ml = MLClassifierStrategy(ml_params, SHARED)
    dfs_fit = {k: v[v.index <= "2022-09-30"] for k, v in dfs.items()}
    ml.fit(dfs_fit)
    signal_sanity("ml_classifier", ml, dfs)
    prefix_test("ml_classifier", ml, dfs, n_cuts=4)

    print("── 4. Engine exec_tf ──────────────────────────────")
    baseline = run_backtest_fast(
        LondonBreakoutStrategy(BREAKOUT_PARAMS, SHARED), SHARED, dfs_full)
    explicit = run_backtest_fast(
        LondonBreakoutStrategy(BREAKOUT_PARAMS, SHARED), SHARED, dfs_full, exec_tf="H1")
    same = [(t.entry_time, t.profit_pts) for t in baseline] == \
           [(t.entry_time, t.profit_pts) for t in explicit]
    check("exec_tf=H1 default identical", same)
    exec_tf_test(dfs_full)

    print("───────────────────────────────────────────────────")
    if FAILURES:
        print(f"✗ {len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("✓ all smoke tests passed")


if __name__ == "__main__":
    main()
