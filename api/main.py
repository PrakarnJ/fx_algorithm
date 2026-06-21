"""FX Algorithm Platform — FastAPI backend entry point."""
import sys
from pathlib import Path

# Make project root importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routers import algorithms, backtest, logs, replay, stocks
from config import FRONTEND_DIST

PLATFORM_VERSION = "2.1.0"

app = FastAPI(
    title="FX Algorithm Platform",
    version=PLATFORM_VERSION,
    description="Multi-asset algorithmic trading research platform.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(algorithms.router, prefix="/api")
app.include_router(stocks.router, prefix="/api")
app.include_router(backtest.router, prefix="/api")
app.include_router(replay.router, prefix="/api")
app.include_router(logs.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok", "version": PLATFORM_VERSION}


# Serve built React frontend in production (after npm run build)
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
