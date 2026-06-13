"""
Main trading bot loop.
Run: python bot.py
MT5 terminal must be open and logged in before starting.

After running backtest/compare.py, set ACTIVE_STRATEGY in config.py
to 'trend' or 'breakout' based on the walk-forward winner.
"""
import time
import logging
from dataclasses import replace
from datetime import datetime, timezone

import MetaTrader5 as mt5

import mt5_connector as conn
import executor
import trade_manager
from risk_manager import calculate_lot, DrawdownGuard
from config import (
    SYMBOL, MAGIC, SHARED, TREND_PARAMS, BREAKOUT_PARAMS, REGIME_PARAMS,
    TF_M15, TF_H1, TF_H4, ACTIVE_STRATEGY,
)
from strategies.trend_following import TrendFollowingStrategy
from strategies.london_breakout import LondonBreakoutStrategy
from strategies.regime_switch import RegimeSwitchStrategy

# A "far" TP (used by the trend leg, which exits via trailing stop, not a
# fixed target). Sent to MT5 as 0.0 = no take-profit.
FAR_TP_THRESHOLD = 100_000


def _build_strategy():
    """Return (strategy, shared). regime_switch needs a wider trailing stop
    than the default SHARED so trends can run — apply it to the shared that
    the live management loop also uses."""
    if ACTIVE_STRATEGY == "trend":
        return TrendFollowingStrategy(TREND_PARAMS, SHARED), SHARED
    if ACTIVE_STRATEGY == "regime_switch":
        shared = replace(
            SHARED,
            breakeven_atr_mult=REGIME_PARAMS.trend_breakeven_atr_mult,
            trail_atr_mult=REGIME_PARAMS.trend_trail_atr_mult,
        )
        return RegimeSwitchStrategy(REGIME_PARAMS, shared), shared
    return LondonBreakoutStrategy(BREAKOUT_PARAMS, SHARED), SHARED

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

LOOP_INTERVAL = 60  # seconds


def _parse_atr_from_comment(comment: str) -> float:
    try:
        return float(comment.split("atr=")[1].split()[0])
    except Exception:
        return 0.0


def run():
    account = conn.connect()
    log.info(f"Connected: {account['login']}  balance={account['balance']:.2f} {account['currency']}")

    strategy, shared = _build_strategy()
    log.info(f"Strategy: {ACTIVE_STRATEGY}  (trail={shared.trail_atr_mult}x ATR, "
             f"risk={shared.risk_pct:.1%}/trade)")
    guard = DrawdownGuard(shared)

    try:
        while True:
            now = datetime.now(tz=timezone.utc)
            account = conn.get_account_info()
            balance = account["balance"]
            guard.set_session_balance(balance)

            # ── Manage any open position ──────────────────────────────────
            positions = conn.get_open_positions(symbol=SYMBOL, magic=MAGIC)
            for pos in positions:
                tick = mt5.symbol_info_tick(SYMBOL)
                is_buy = pos["type"] == mt5.ORDER_TYPE_BUY
                current_price = tick.bid if is_buy else tick.ask
                atr_val = _parse_atr_from_comment(pos.get("comment", ""))
                direction = "buy" if is_buy else "sell"

                new_sl = trade_manager.update_sl(
                    direction, pos["price_open"], pos["sl"], atr_val, current_price, shared
                )
                if abs(new_sl - pos["sl"]) > 1e-5:
                    if executor.modify_sl(pos["ticket"], new_sl):
                        log.info(f"SL updated  ticket={pos['ticket']}  {pos['sl']:.2f} → {new_sl:.2f}")

            # ── Check for new entry ───────────────────────────────────────
            if not positions and guard.is_allowed(balance, now):
                symbol_info = conn.get_symbol_info(SYMBOL)
                if symbol_info.spread > shared.max_spread_points:
                    log.debug(f"Spread {symbol_info.spread} > max, skipping")
                else:
                    dfs = {
                        "M15": conn.get_rates(SYMBOL, TF_M15, 600),
                        "H1":  conn.get_rates(SYMBOL, TF_H1,  500),
                        "H4":  conn.get_rates(SYMBOL, TF_H4,  300),
                    }
                    signal = strategy.get_signal(dfs)
                    if signal:
                        sl_distance = abs(signal.entry_price - signal.sl)
                        lot = calculate_lot(balance, shared.risk_pct, sl_distance, symbol_info)
                        # Trend leg has no fixed TP (rides the trailing stop) —
                        # send 0.0 to MT5 instead of the far placeholder TP.
                        tp = 0.0 if abs(signal.tp - signal.entry_price) > FAR_TP_THRESHOLD else signal.tp
                        comment = f"atr={signal.atr:.5f}"
                        executor.place_order(SYMBOL, signal.direction, lot, signal.sl, tp, MAGIC, comment)
                        log.info(
                            f"ORDER  {signal.direction.upper()}  {lot} lots  "
                            f"entry≈{signal.entry_price:.2f}  SL={signal.sl:.2f}  "
                            f"TP={'trail' if tp == 0.0 else f'{tp:.2f}'}"
                        )

            time.sleep(LOOP_INTERVAL)

    except KeyboardInterrupt:
        log.info("Bot stopped")
    finally:
        conn.disconnect()


if __name__ == "__main__":
    run()
