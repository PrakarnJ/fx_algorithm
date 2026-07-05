"""XAUUSD Pine Studio — FastAPI backend entry point."""
import sys
from pathlib import Path

# Make project root importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routers import chart, logs, pine
from config import FRONTEND_DIST

PLATFORM_VERSION = "3.0.0"

app = FastAPI(
    title="XAUUSD Pine Studio",
    version=PLATFORM_VERSION,
    description="Paste a TradingView Pine Script, plot it on the gold chart, backtest it.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chart.router, prefix="/api")
app.include_router(pine.router, prefix="/api")
app.include_router(logs.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok", "version": PLATFORM_VERSION}


# Serve built React frontend in production (after npm run build)
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
