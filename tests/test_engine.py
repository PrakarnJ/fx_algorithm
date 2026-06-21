"""
Backtest engine edge-case tests.

All tests use synthetic data only — no CSV files required.

Bar layout (H1, n=310):
  bars[0..249]  : warmup, skipped by engine
  bars[250]     : warmup_time threshold (first eligible bar)
  bars[260]     : signal bar — trade opens here
  bars[261]     : first management bar (open_bars=1)
  bars[262]     : second management bar (open_bars=2)
"""
import numpy as np
import pandas as pd
import pytest

from config import SharedParams
from backtest.engine import run_backtest_fast

# ── helpers ──────────────────────────────────────────────────────────────────

PRICE   = 2000.0
SIG_IDX = 260      # index in H1 bars where the signal fires


def _flat_h1(n: int = 310, high_offset: float = 1.0, low_offset: float = 1.0) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    p = np.full(n, PRICE)
    return pd.DataFrame({
        "open":  p,
        "high":  p + high_offset,
        "low":   p - low_offset,
        "close": p,
    }, index=idx)


def _patch_bar(df: pd.DataFrame, i: int, **kwargs) -> pd.DataFrame:
    df = df.copy()
    for col, val in kwargs.items():
        df.iloc[i, df.columns.get_loc(col)] = val
    return df


def _make_dfs(h1: pd.DataFrame) -> dict:
    m15 = h1.resample("15min").ffill()
    h4  = h1.resample("4h").first().ffill()
    return {"M15": m15, "H1": h1, "H4": h4}


def _one_signal(h1: pd.DataFrame, direction: str = "buy",
                sl_dist: float = 10.0, tp_dist: float = 20.0,
                atr: float = 5.0, partial_tp_dist: float | None = None) -> pd.DataFrame:
    """Build a single-row signals DataFrame at SIG_IDX."""
    entry = PRICE
    if direction == "buy":
        sl = entry - sl_dist
        tp = entry + tp_dist
        ptp = (entry + partial_tp_dist) if partial_tp_dist else float("nan")
    else:
        sl = entry + sl_dist
        tp = entry - tp_dist
        ptp = (entry - partial_tp_dist) if partial_tp_dist else float("nan")
    bar_time = h1.index[SIG_IDX]
    return pd.DataFrame(
        [{"direction": direction, "entry": entry, "sl": sl, "tp": tp,
          "atr": atr, "partial_tp": ptp}],
        index=[bar_time],
    )


# ── basic fill ────────────────────────────────────────────────────────────────

def test_trade_fills():
    """A signal past warmup should produce exactly one trade."""
    h1 = _flat_h1()
    dfs = _make_dfs(h1)
    sig = _one_signal(h1, tp_dist=5000.0)  # far TP so engine force-closes at end
    strat = _StubStrategy(sig)
    trades = run_backtest_fast(strat, SharedParams(), dfs, spread_points=0)
    assert len(trades) == 1


# ── SL vs TP: conservative same-bar fill ─────────────────────────────────────

def test_sl_wins_when_both_hit_same_bar():
    """When both SL and TP are breached in the same bar, SL should fill (conservative)."""
    h1 = _flat_h1()
    # Bar 261: spike both ways
    mgmt_bar = SIG_IDX + 1
    h1 = _patch_bar(h1, mgmt_bar, high=PRICE + 25.0, low=PRICE - 15.0)
    dfs = _make_dfs(h1)
    sig = _one_signal(h1, sl_dist=10.0, tp_dist=20.0)
    strat = _StubStrategy(sig)
    trades = run_backtest_fast(strat, SharedParams(), dfs, spread_points=0)
    assert len(trades) == 1
    t = trades[0]
    assert t.profit_pts < 0, "SL hit → loss expected"
    assert abs(t.exit_price - (PRICE - 10.0)) < 1e-6, "exit at SL price"


def test_tp_hit():
    """When only TP is breached, trade closes at TP."""
    h1 = _flat_h1()
    mgmt_bar = SIG_IDX + 1
    h1 = _patch_bar(h1, mgmt_bar, high=PRICE + 25.0, low=PRICE - 5.0)
    dfs = _make_dfs(h1)
    sig = _one_signal(h1, sl_dist=10.0, tp_dist=20.0)
    strat = _StubStrategy(sig)
    trades = run_backtest_fast(strat, SharedParams(), dfs, spread_points=0)
    assert len(trades) == 1
    assert abs(trades[0].profit_pts - 20.0) < 1e-6


# ── partial TP ────────────────────────────────────────────────────────────────

def test_partial_tp_then_full_tp():
    """Partial TP at 10 pts, full TP at 30 pts: profit = 0.5×10 + 0.5×30 = 20."""
    h1 = _flat_h1()
    # Bar 261: partial TP fires (high=+15 ≥ partial_tp=+10).  low must stay ABOVE
    # entry (2000) so the engine's same-bar SL check doesn't close at break-even.
    h1 = _patch_bar(h1, SIG_IDX + 1, high=PRICE + 15.0, low=PRICE + 0.5)
    # Bar 262: full TP (high reaches +35, low stays above new SL at entry)
    h1 = _patch_bar(h1, SIG_IDX + 2, high=PRICE + 35.0, low=PRICE + 1.0)
    dfs = _make_dfs(h1)
    sig = _one_signal(h1, sl_dist=10.0, tp_dist=30.0, partial_tp_dist=10.0)
    strat = _StubStrategy(sig)
    trades = run_backtest_fast(strat, SharedParams(), dfs, spread_points=0)
    assert len(trades) == 1
    assert abs(trades[0].profit_pts - 20.0) < 1e-6


def test_partial_tp_then_sl():
    """Partial TP then SL at break-even: profit = 0.5×10 + 0.5×0 = 5."""
    h1 = _flat_h1()
    h1 = _patch_bar(h1, SIG_IDX + 1, high=PRICE + 15.0, low=PRICE - 5.0)
    # Bar 262: SL at break-even (entry=2000) hit
    h1 = _patch_bar(h1, SIG_IDX + 2, high=PRICE + 1.0, low=PRICE - 1.0)
    # engine moves SL to entry after partial; ensure low touches entry
    h1 = _patch_bar(h1, SIG_IDX + 2, low=PRICE - 0.5)  # low just below entry
    dfs = _make_dfs(h1)
    sig = _one_signal(h1, sl_dist=10.0, tp_dist=30.0, partial_tp_dist=10.0, atr=0.0)
    strat = _StubStrategy(sig)
    # atr=0 disables trailing, SL stays at break-even (entry) after partial
    trades = run_backtest_fast(strat, SharedParams(), dfs, spread_points=0)
    assert len(trades) == 1
    assert abs(trades[0].profit_pts - 5.0) < 1e-6


# ── time-stop ─────────────────────────────────────────────────────────────────

def test_time_stop_closes_after_n_bars():
    """Trade with time_stop=2 closes at close of bar 262 (open_bars reaches 2)."""
    h1 = _flat_h1(high_offset=0.5, low_offset=0.5)  # tight spread: SL/TP won't hit
    dfs = _make_dfs(h1)
    sig = _one_signal(h1, sl_dist=500.0, tp_dist=500.0, atr=0.0)
    strat = _StubStrategy(sig, time_stop=2)
    trades = run_backtest_fast(strat, SharedParams(), dfs, spread_points=0)
    assert len(trades) == 1
    t = trades[0]
    assert t.exit_time == h1.index[SIG_IDX + 2]
    assert abs(t.exit_price - PRICE) < 1e-6  # closed at bar close


# ── consecutive-loss pause ────────────────────────────────────────────────────

def test_pause_after_consecutive_losses():
    """After max_consec_losses consecutive losses the next signals are skipped."""
    n = 400
    h1 = _flat_h1(n)
    # Alternate: signal bars, then SL-hit bars
    rows = []
    for k in range(4):
        sig_i  = SIG_IDX + k * 3          # signal bar
        hit_i  = sig_i + 1                 # SL hit on next bar
        t      = h1.index[sig_i]
        entry  = PRICE
        rows.append({"direction": "buy", "entry": entry, "sl": entry - 5.0,
                     "tp": entry + 5000.0, "atr": 0.0, "partial_tp": float("nan")})
        h1 = _patch_bar(h1, hit_i, low=entry - 10.0)

    sig_df = pd.DataFrame(rows, index=[h1.index[SIG_IDX + k * 3] for k in range(4)])
    shared = SharedParams(max_consec_losses=2, consec_loss_pause_hours=48)
    strat = _StubStrategy(sig_df)
    trades = run_backtest_fast(strat, shared, _make_dfs(h1), spread_points=0)

    # First 2 signals → 2 losing trades; 3rd signal inside pause window → skipped
    assert len(trades) == 2
    assert all(t.profit_pts < 0 for t in trades)


# ── transaction cost model ────────────────────────────────────────────────────

def test_commission_deducted():
    """Commission (100 pts = 1.0 price unit) is deducted from profit_pts."""
    h1 = _flat_h1()
    h1 = _patch_bar(h1, SIG_IDX + 1, high=PRICE + 25.0, low=PRICE - 5.0)
    dfs = _make_dfs(h1)
    sig = _one_signal(h1, sl_dist=10.0, tp_dist=20.0, atr=0.0)

    no_cost  = run_backtest_fast(_StubStrategy(sig), SharedParams(), dfs, spread_points=0)
    with_cost = run_backtest_fast(
        _StubStrategy(sig),
        SharedParams(commission_pts=100),  # 100 pts = 1.0 price unit
        dfs, spread_points=0,
    )
    assert len(no_cost) == 1 and len(with_cost) == 1
    assert abs(no_cost[0].profit_pts - with_cost[0].profit_pts - 1.0) < 1e-9


def test_slippage_worsens_sl_fill():
    """slippage_pts worsens SL exit price and reduces (magnifies loss) profit_pts."""
    h1 = _flat_h1()
    h1 = _patch_bar(h1, SIG_IDX + 1, high=PRICE + 5.0, low=PRICE - 15.0)
    dfs = _make_dfs(h1)
    sig = _one_signal(h1, sl_dist=10.0, tp_dist=20.0, atr=0.0)

    no_slip  = run_backtest_fast(_StubStrategy(sig), SharedParams(), dfs, spread_points=0)
    with_slip = run_backtest_fast(
        _StubStrategy(sig),
        SharedParams(slippage_pts=50),   # 50 pts = 0.5 price unit worse fill
        dfs, spread_points=0,
    )
    assert len(no_slip) == 1 and len(with_slip) == 1
    # With slip: exit at SL-0.50, so loss is 0.50 bigger
    assert abs(with_slip[0].profit_pts - no_slip[0].profit_pts + 0.5) < 1e-9
    assert abs(with_slip[0].exit_price - (PRICE - 10.0 - 0.5)) < 1e-6


def test_swap_deducted_per_night():
    """swap_pts_per_night is deducted proportional to calendar nights held."""
    # Use time_stop=3 so the trade is open for 3 hours (= 0 calendar nights since
    # same UTC day).  Then use time_stop=25 to cross a midnight.
    h1 = _flat_h1(n=310, high_offset=0.5, low_offset=0.5)
    dfs = _make_dfs(h1)
    sig = _one_signal(h1, sl_dist=500.0, tp_dist=500.0, atr=0.0)

    no_swap   = run_backtest_fast(_StubStrategy(sig, time_stop=3),
                                  SharedParams(), dfs, spread_points=0)
    with_swap = run_backtest_fast(_StubStrategy(sig, time_stop=3),
                                  SharedParams(swap_pts_per_night=100), dfs, spread_points=0)
    assert len(no_swap) == 1 and len(with_swap) == 1

    entry_t = no_swap[0].entry_time
    exit_t  = no_swap[0].exit_time
    nights  = max(0, (exit_t - entry_t).days)
    expected_swap = nights * 100 * 0.01
    assert abs(no_swap[0].profit_pts - with_swap[0].profit_pts - expected_swap) < 1e-9


# ── internal stub ─────────────────────────────────────────────────────────────

class _StubStrategy:
    exec_tf = "H1"

    def __init__(self, signals_df, *, time_stop: int = 0,
                 full_close_at_partial: bool = False):
        self._signals = signals_df

        class _P:
            pass

        self.p = _P()
        self.p.time_stop_hours = time_stop
        self.p.full_close_at_partial = full_close_at_partial

    def generate_signals(self, dfs):
        return self._signals
