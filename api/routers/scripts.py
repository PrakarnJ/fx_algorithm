"""Saved Pine scripts — CRUD over the SQLite store."""
from fastapi import APIRouter, HTTPException

from api import store
from api.logger import log_event
from api.schemas import (ScriptCreate, ScriptDetail, ScriptListResponse,
                         ScriptUpdate)

router = APIRouter(tags=["scripts"])


@router.get("/scripts", response_model=ScriptListResponse)
def list_scripts():
    return ScriptListResponse(scripts=store.list_scripts())


@router.get("/scripts/{script_id}", response_model=ScriptDetail)
def get_script(script_id: int):
    try:
        return ScriptDetail(**store.get_script(script_id))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/scripts", response_model=ScriptDetail)
def create_script(req: ScriptCreate):
    try:
        row = store.create_script(req.name, req.source)
    except ValueError as e:
        status = 409 if "already exists" in str(e) else 400
        raise HTTPException(status_code=status, detail=str(e))
    log_event("script_saved", script_id=row["id"], name=row["name"])
    return ScriptDetail(**row)


@router.put("/scripts/{script_id}", response_model=ScriptDetail)
def update_script(script_id: int, req: ScriptUpdate):
    try:
        row = store.update_script(script_id, name=req.name, source=req.source)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        status = 409 if "already exists" in str(e) else 400
        raise HTTPException(status_code=status, detail=str(e))
    log_event("script_saved", script_id=row["id"], name=row["name"])
    return ScriptDetail(**row)


@router.delete("/scripts/{script_id}")
def delete_script(script_id: int):
    try:
        store.delete_script(script_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    log_event("script_deleted", script_id=script_id)
    return {"ok": True}
