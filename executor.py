import time
import MetaTrader5 as mt5
from config import MAGIC


def place_order(
    symbol: str,
    direction: str,
    lot: float,
    sl: float,
    tp: float,
    magic: int = MAGIC,
    comment: str = "",
) -> dict:
    order_type = mt5.ORDER_TYPE_BUY if direction == "buy" else mt5.ORDER_TYPE_SELL
    tick = mt5.symbol_info_tick(symbol)
    price = tick.ask if direction == "buy" else tick.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 20,
        "magic": magic,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    for _ in range(3):
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            return result._asdict()
        if result.retcode in (mt5.TRADE_RETCODE_REQUOTE, mt5.TRADE_RETCODE_PRICE_CHANGED):
            tick = mt5.symbol_info_tick(symbol)
            request["price"] = tick.ask if direction == "buy" else tick.bid
            time.sleep(0.5)
            continue
        raise RuntimeError(f"Order rejected: retcode={result.retcode} {result.comment}")

    raise RuntimeError("Order failed after 3 requote retries")


def modify_sl(ticket: int, new_sl: float) -> bool:
    result = mt5.order_send({
        "action": mt5.TRADE_ACTION_SLTP,
        "position": ticket,
        "sl": new_sl,
    })
    return result.retcode == mt5.TRADE_RETCODE_DONE


def close_position(position: dict) -> bool:
    is_buy = position["type"] == mt5.ORDER_TYPE_BUY
    close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
    tick = mt5.symbol_info_tick(position["symbol"])
    price = tick.bid if is_buy else tick.ask

    result = mt5.order_send({
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": position["symbol"],
        "volume": position["volume"],
        "type": close_type,
        "position": position["ticket"],
        "price": price,
        "deviation": 20,
        "magic": position["magic"],
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    })
    return result.retcode == mt5.TRADE_RETCODE_DONE
