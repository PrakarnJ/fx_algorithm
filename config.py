"""Global configuration — XAUUSD Pine-Script studio."""
from pathlib import Path

ROOT_DIR = Path(__file__).parent
DATA_DIR = ROOT_DIR / "data"
LOGS_DIR = ROOT_DIR / "logs"
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"

SYMBOL = "XAUUSD"

# SQLite store for saved Pine scripts (and future tables).
DB_PATH = DATA_DIR / "pine_studio.db"

# Guard against accidentally huge runs — M15 full history is ~150k bars,
# the bar-by-bar interpreter handles ~10-20k bars/s.
MAX_BARS = 200_000

# Timeframe key → CSV filename in data/ (single source of truth for gold bars).
TF_TO_FILE = {
    "M15": f"{SYMBOL}_M15.csv",
    "H1": f"{SYMBOL}_H1.csv",
    "H4": f"{SYMBOL}_H4.csv",
}

# XAUUSD contract/cost defaults — seed the strategy tester when a Pine script
# omits them. 1 point = $0.01 in price; TradingView's tester works in price
# units and currency, so we express costs the same way.
TICK_SIZE = 0.01
DEFAULT_INITIAL_CAPITAL = 100_000.0
DEFAULT_QTY_TYPE = "fixed"       # "fixed" | "percent_of_equity" | "cash"
DEFAULT_QTY_VALUE = 1.0
DEFAULT_COMMISSION_TYPE = "none"  # "none" | "percent" | "cash_per_contract" | "cash_per_order"
DEFAULT_COMMISSION_VALUE = 0.0
DEFAULT_SPREAD_POINTS = 0         # TV's tester has no spread by default
