import MetaTrader5 as mt5
import pandas as pd


def connect(login: int = None, password: str = None, server: str = None, path: str = None) -> dict:
    kwargs = {}
    if path:
        kwargs["path"] = path
    if login:
        kwargs["login"] = login
    if password:
        kwargs["password"] = password
    if server:
        kwargs["server"] = server

    if not mt5.initialize(**kwargs):
        raise ConnectionError(f"MT5 initialize failed: {mt5.last_error()}")

    info = mt5.account_info()
    if info is None:
        raise ConnectionError(f"Account info unavailable: {mt5.last_error()}")
    return info._asdict()


def disconnect() -> None:
    mt5.shutdown()


def get_rates(symbol: str, timeframe: int, n_bars: int = 600) -> pd.DataFrame:
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n_bars)
    if rates is None or len(rates) == 0:
        raise ValueError(f"No rates for {symbol} tf={timeframe}: {mt5.last_error()}")
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    return df


def get_account_info() -> dict:
    info = mt5.account_info()
    if info is None:
        raise RuntimeError(f"Cannot get account info: {mt5.last_error()}")
    return info._asdict()


def get_symbol_info(symbol: str):
    info = mt5.symbol_info(symbol)
    if info is None:
        raise ValueError(f"Symbol {symbol} not found: {mt5.last_error()}")
    return info


def get_open_positions(symbol: str = None, magic: int = None) -> list:
    positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    if positions is None:
        return []
    result = [p._asdict() for p in positions]
    if magic is not None:
        result = [p for p in result if p["magic"] == magic]
    return result
