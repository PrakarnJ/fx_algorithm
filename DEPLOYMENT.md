# Deployment Guide — Regime-Aware Switch on MT5 (DEMO FIRST)

> ⚠️ **Read this fully before risking any money.** This strategy passed walk-forward
> backtesting on real gold data (PF 1.77 OOS) but has **never been forward-tested**,
> and ~69% of its backtested profit came from a single 2026 trend. It is wired up
> for **demo trading only**. Treat live deployment as an experiment, not a money machine.

---

## 0. Reality check — what this is and isn't

- ✅ It's a regime-aware system: rides trends (Donchian breakout + ATR trailing on H4),
  stands aside when the market is ranging (current config: `range_enabled=False`).
- ✅ It survived honest walk-forward validation on real 2022–2026 XAUUSD data.
- ❌ It is **not** proven on future/unseen data — that's what the demo phase is for.
- ❌ The edge is **tail-dependent** (a few big trend captures carry the profit). Expect
  long flat or losing stretches between big trends. This is normal for trend-following.
- ❌ There is **no guaranteed-good parameter set**. `config.py:REGIME_PARAMS` was optimized
  on the most recent 12 months. Re-derive it periodically (see §6).

---

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| **Windows PC or VPS** | The `MetaTrader5` Python package only installs on Windows. A Mac/Linux box **cannot** run `bot.py`. A cheap Windows VPS keeps it running 24/5. |
| **MT5 terminal** | Installed, logged into your broker, with a **demo account** to start. |
| **Python 3.9+** | On the same Windows machine as the terminal. |
| **A broker that offers XAUUSD** | Check the symbol name — some brokers use `XAUUSD`, `GOLD`, `XAUUSD.m`, etc. Update `SYMBOL` in `config.py` if needed. |

---

## 2. One-time setup (on Windows)

```bash
# clone your repo onto the Windows machine, then:
python -m venv .venv
.venv\Scripts\pip install MetaTrader5 pandas numpy
```

In the MT5 terminal:
1. Log into your **demo** account.
2. Tools → Options → Expert Advisors → tick **"Allow algorithmic trading"**.
3. Click the **"Algo Trading"** toolbar button so it's green.
4. Make sure the XAUUSD chart is open and receiving ticks.

Confirm the symbol name your broker uses and that `config.py:SYMBOL` matches.

---

## 3. Pre-flight checks (do these before every first run)

```bash
.venv\Scripts\python -c "import MetaTrader5 as m; print(m.initialize(), m.version())"
.venv\Scripts\python -c "import mt5_connector as c; print(c.connect())"   # should print account dict
```

Verify in `config.py`:
- `ACTIVE_STRATEGY = "regime_switch"` ✅ (already set)
- `SHARED.risk_pct` — **start at 0.005 (0.5%) or lower** for the first live phase.
- `SHARED.daily_loss_stop_pct` and `max_consec_losses` — the built-in circuit breakers.

---

## 4. Run the bot

```bash
.venv\Scripts\python bot.py
```

It loops every 60s:
1. Manages any open position (break-even + ATR trailing stop via `trade_manager.update_sl`).
2. If flat, checks `RegimeSwitchStrategy.get_signal()` for a new entry.
3. Sizes the position to risk `SHARED.risk_pct` of balance per trade.
4. Logs every action. Stop it with **Ctrl-C** (closes the MT5 connection cleanly).

**Note:** the strategy trades on **H4 bars**, so signals are infrequent — it may do nothing
for days. That's expected. No signal ≠ broken.

---

## 5. The deployment ladder — DO NOT SKIP STEPS

```
[1] DEMO            run ≥ 1–2 months. Must span both a trend AND a range period.
       │            Compare live demo stats to backtest. If they roughly agree → next.
       ▼
[2] MICRO-LIVE      smallest lot (0.01), risk 0.25–0.5%. Real fills, real slippage.
       │            Run ≥ 1 month. Confirm execution quality matches demo.
       ▼
[3] SCALE SLOWLY    raise risk in small steps only after sustained agreement with
                    expectations. Never add size to recover a drawdown.
```

**Abort criteria (drop back a rung or stop):**
- Live results materially worse than backtest after enough trades (≥ 20–30).
- Drawdown exceeds what the backtest showed for a comparable period.
- Broker spread/slippage on XAUUSD is much higher than the 20-point backtest assumption.

---

## 6. Re-deriving parameters (important — markets drift)

Walk-forward *re-optimizes every window*; the live `REGIME_PARAMS` is a snapshot from the
last 12 months and **will go stale**. Refresh it on a schedule (e.g. quarterly) on your
dev machine with fresh data:

```bash
# 1. update data (real bars):
python data/convert_dukascopy.py /path/to/new/dukascopy/csvs
# 2. re-run walk-forward to confirm the method still holds:
python backtest/walkforward.py --family regime_switch --trials 40
# 3. re-optimize REGIME_PARAMS on the latest 12 months and paste into config.py
#    (the one-off optimization snippet used to derive the current values).
```

If walk-forward stops being profitable on fresh data, **stop trading it** — the regime
it exploited may be gone.

---

## 7. Safety / monitoring

- **Built-in guards** (`risk_manager.DrawdownGuard`): pauses 24h after `max_consec_losses`
  losses; halts the day after `daily_loss_stop_pct` loss. Keep these on.
- **Kill switch:** Ctrl-C, or turn off "Algo Trading" in MT5, or close the terminal.
- **Watch:** balance/equity curve, number of open positions (should be ≤ 1), the bot's log
  for `ORDER` / `SL updated` lines and any `RuntimeError` from the executor.
- **VPS:** if running unattended, set the terminal + bot to auto-start, and check daily.

---

## 8. Honest bottom line

This is a research-grade strategy with a real but fragile edge, deployed for **learning and
demo validation**. The disciplined path — demo → micro → scale, with periodic re-validation —
is what separates a sustainable system from blowing up an account on a backtest that looked
good. If the demo phase doesn't reproduce the backtest, that's the system telling you the
truth. Listen to it.
