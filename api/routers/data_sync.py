"""Data sync endpoints — trigger and poll the Dukascopy download."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api import sync

router = APIRouter(tags=["data"])


class SyncStartRequest(BaseModel):
    mode: str = "auto"  # "auto" | "full"


@router.post("/data/sync", status_code=202)
def start_sync(req: SyncStartRequest | None = None):
    mode = req.mode if req else "auto"
    if mode not in ("auto", "full"):
        raise HTTPException(status_code=400, detail="mode must be 'auto' or 'full'")
    resolved = sync.start_sync(mode)
    if resolved is None:
        raise HTTPException(status_code=409, detail="a sync is already running")
    return {"status": "started", "mode": resolved}


@router.get("/data/sync/status")
def sync_status():
    return sync.get_status()
