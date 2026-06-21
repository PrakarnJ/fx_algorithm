import asyncio
import uuid
from typing import List, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from api.runner import run_backtest_job, get_job, get_all_results
from api.schemas import BacktestJobStatus, BacktestRequest, ComboResult

router = APIRouter(tags=["backtest"])

# Map job_id → set of active WebSocket connections for progress streaming
_job_ws: dict[str, list] = {}


@router.post("/backtest/run")
async def start_backtest(req: BacktestRequest):
    job_id = str(uuid.uuid4())
    _job_ws[job_id] = []

    async def broadcast(msg: dict):
        dead = []
        for ws in _job_ws.get(job_id, []):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            _job_ws[job_id].remove(ws)

    asyncio.create_task(
        run_backtest_job(
            job_id=job_id,
            algo_names=req.algo_names,
            symbols=req.symbols,
            spread_overrides=req.spread_overrides,
            ws_broadcast=broadcast,
            start_date=req.start_date,
            end_date=req.end_date,
        )
    )
    return {"job_id": job_id}


@router.get("/backtest/status/{job_id}", response_model=BacktestJobStatus)
def get_job_status(job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/backtest/results", response_model=list[ComboResult])
def list_results():
    return get_all_results()


@router.websocket("/ws/backtest/{job_id}")
async def backtest_ws(websocket: WebSocket, job_id: str):
    await websocket.accept()
    if job_id not in _job_ws:
        _job_ws[job_id] = []
    _job_ws[job_id].append(websocket)

    # Send current state immediately (client may connect after job started)
    job = get_job(job_id)
    if job:
        await websocket.send_json({"type": "status", **job.model_dump()})

    try:
        while True:
            # Keep connection alive; broadcast() handles outbound messages
            await asyncio.sleep(30)
    except WebSocketDisconnect:
        if websocket in _job_ws.get(job_id, []):
            _job_ws[job_id].remove(websocket)
