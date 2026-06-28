import asyncio
import shutil
import uuid

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from algorithms.registry import TF_TO_FILE
from api.logger import log_event
from api.schemas import DownloadRequest, SymbolInfo, SyncAllRequest
from config import STOCKS_DIR
from data_pipeline.capabilities import available_tfs
from data_pipeline.downloader import download
from stocks.loader import list_symbols, get_symbol_meta, get_yf_ticker

router = APIRouter(tags=["stocks"])

# In-memory download job progress
_download_jobs: dict = {}


def _read_last_date_str(path) -> str | None:
    """Read the last bar's date from a CSV by scanning its final bytes — no full load."""
    if path is None or not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 256))
            tail = f.read().decode(errors="ignore")
        last_line = tail.strip().rsplit("\n", 1)[-1]
        ts = last_line.split(",")[0].strip()
        return ts[:10] if len(ts) >= 10 else None
    except Exception:
        return None


@router.get("/stocks", response_model=list[SymbolInfo])
def get_stocks():
    symbols = list_symbols()
    result = []
    for sym in symbols:
        meta = get_symbol_meta(sym)
        sym_dir = STOCKS_DIR / sym
        last_synced = None
        newest_path = None
        for filename in TF_TO_FILE.values():
            path = sym_dir / filename
            if path.exists():
                mtime = path.stat().st_mtime
                if last_synced is None or mtime > last_synced:
                    last_synced = mtime
                    newest_path = path
        last_data_date = _read_last_date_str(newest_path)
        result.append(SymbolInfo(
            symbol=sym,
            name=meta.get("name", sym),
            tick_size=meta.get("tick_size", 0.01),
            spread_points=meta.get("spread_points", 20),
            yfinance_ticker=meta.get("yfinance_ticker", sym),
            available_tfs=available_tfs(sym),
            last_synced=last_synced,
            last_data_date=last_data_date,
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


# Default TFs to sync when a symbol has no existing data yet
_DEFAULT_SYNC_TFS = ["H1", "H4", "D1"]


@router.post("/stocks/sync-all")
async def sync_all(req: SyncAllRequest):
    """Incrementally sync all (or selected) registered symbols up to today."""
    symbols = req.symbols if req.symbols else list_symbols()
    job_id = str(uuid.uuid4())
    _download_jobs[job_id] = {"status": "running", "progress": [], "done": 0, "total": 0}
    log_event("data_sync_all_start", job_id=job_id, symbols=symbols)

    async def _run():
        total_work = len(symbols)
        _download_jobs[job_id]["total"] = total_work

        for sym in symbols:
            yf_ticker = get_yf_ticker(sym)
            tfs = available_tfs(sym) or _DEFAULT_SYNC_TFS
            try:
                results = await asyncio.to_thread(
                    download, sym, yf_ticker, tfs, STOCKS_DIR, None, True
                )
                _download_jobs[job_id]["progress"].append(
                    {"symbol": sym, "status": "done", "bars": results})
                log_event("data_sync_done", symbol=sym, bars=results)
            except Exception as e:
                _download_jobs[job_id]["progress"].append(
                    {"symbol": sym, "status": "error", "error": str(e)})
                log_event("data_sync_error", symbol=sym, error=str(e))
            _download_jobs[job_id]["done"] += 1

        _download_jobs[job_id]["status"] = "complete"

    asyncio.create_task(_run())
    return {"job_id": job_id}
