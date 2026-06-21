import asyncio
import shutil
import uuid

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from algorithms.registry import TF_TO_FILE
from api.logger import log_event
from api.schemas import DownloadRequest, SymbolInfo
from config import STOCKS_DIR
from data_pipeline.capabilities import available_tfs
from data_pipeline.downloader import download
from stocks.loader import list_symbols, get_symbol_meta, get_yf_ticker

router = APIRouter(tags=["stocks"])

# In-memory download job progress
_download_jobs: dict = {}


@router.get("/stocks", response_model=list[SymbolInfo])
def get_stocks():
    symbols = list_symbols()
    result = []
    for sym in symbols:
        meta = get_symbol_meta(sym)
        result.append(SymbolInfo(
            symbol=sym,
            name=meta.get("name", sym),
            tick_size=meta.get("tick_size", 0.01),
            spread_points=meta.get("spread_points", 20),
            yfinance_ticker=meta.get("yfinance_ticker", sym),
            available_tfs=available_tfs(sym),
        ))
    return result


@router.get("/stocks/{symbol}/info")
def get_stock_info(symbol: str):
    """Return per-TF metadata (bar count, date range, file size, last modified) for a symbol."""
    result = {}
    for tf_key, filename in TF_TO_FILE.items():
        path = STOCKS_DIR / symbol / filename
        if not path.exists():
            continue
        stat = path.stat()
        try:
            df = pd.read_csv(path, index_col="time", parse_dates=True, usecols=["time"])
            bar_count = len(df)
            start_date = str(df.index.min()) if bar_count > 0 else None
            end_date = str(df.index.max()) if bar_count > 0 else None
        except Exception:
            bar_count = 0
            start_date = None
            end_date = None
        result[tf_key] = {
            "bar_count": bar_count,
            "file_size_bytes": stat.st_size,
            "start_date": start_date,
            "end_date": end_date,
            "last_modified": stat.st_mtime,
        }
    return result


@router.delete("/stocks/{symbol}/{tf}")
def delete_symbol_tf(symbol: str, tf: str):
    """Delete a single timeframe CSV file for a symbol."""
    filename = TF_TO_FILE.get(tf)
    if not filename:
        raise HTTPException(status_code=400, detail=f"Unknown TF key: {tf}")
    path = STOCKS_DIR / symbol / filename
    if path.exists():
        path.unlink()
    log_event("stock_data_deleted", symbol=symbol, tf=tf)
    return {"deleted": f"{symbol}/{tf}"}


@router.delete("/stocks/{symbol}")
def delete_symbol(symbol: str):
    """Delete all downloaded data files for a symbol (keeps registry entry)."""
    symbol_dir = STOCKS_DIR / symbol
    if symbol_dir.exists():
        shutil.rmtree(symbol_dir)
    log_event("stock_data_deleted", symbol=symbol, tf="all")
    return {"deleted": symbol}


@router.get("/stocks/{symbol}/data")
def get_stock_data(
    symbol: str,
    tf: str = Query("H1", description="Internal TF key e.g. H1, M15, D1"),
    limit: int = Query(500, ge=10, le=50000),
):
    fname = TF_TO_FILE.get(tf)
    if not fname:
        raise HTTPException(status_code=400, detail=f"Unknown TF key: {tf}")
    path = STOCKS_DIR / symbol / fname
    if not path.exists():
        raise HTTPException(status_code=404,
                            detail=f"No {tf} data for {symbol}. Download first.")
    df = pd.read_csv(path, index_col="time", parse_dates=True).tail(limit)
    records = []
    for t, row in df.iterrows():
        records.append({
            "time": int(pd.Timestamp(t).timestamp()),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
        })
    return {"symbol": symbol, "tf": tf, "bars": records}


@router.post("/stocks/download")
async def start_download(req: DownloadRequest):
    job_id = str(uuid.uuid4())
    _download_jobs[job_id] = {"status": "running", "progress": [], "done": 0, "total": 0}
    log_event("data_download_start", job_id=job_id,
              symbols=req.symbols, tfs=req.internal_tfs)

    async def _run():
        total_work = len(req.symbols) * len(req.internal_tfs)
        _download_jobs[job_id]["total"] = total_work

        for sym in req.symbols:
            yf_ticker = get_yf_ticker(sym)
            try:
                results = await asyncio.to_thread(
                    download, sym, yf_ticker, req.internal_tfs, STOCKS_DIR
                )
                _download_jobs[job_id]["progress"].append(
                    {"symbol": sym, "status": "done", "bars": results})
                _download_jobs[job_id]["done"] += len(req.internal_tfs)
                log_event("data_download_done", symbol=sym, bars=results)
            except Exception as e:
                _download_jobs[job_id]["progress"].append(
                    {"symbol": sym, "status": "error", "error": str(e)})
                _download_jobs[job_id]["done"] += len(req.internal_tfs)
                log_event("data_download_error", symbol=sym, error=str(e))

        _download_jobs[job_id]["status"] = "complete"

    asyncio.create_task(_run())
    return {"job_id": job_id}


@router.get("/stocks/download/{job_id}")
def get_download_status(job_id: str):
    job = _download_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
