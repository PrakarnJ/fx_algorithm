from typing import Optional

from fastapi import APIRouter, Query

from api.logger import read_logs

router = APIRouter(tags=["logs"])


@router.get("/logs")
def get_logs(
    limit: int = Query(200, ge=1, le=5000),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
):
    return {"logs": read_logs(limit=limit, event_type=event_type)}
