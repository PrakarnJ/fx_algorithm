"""Ranking — backtest several saved scripts on the same bars and compare."""
from fastapi import APIRouter, HTTPException

from api import store
from api.logger import log_event
from api.schemas import RankingItem, RankingRequest, RankingResponse
from config import MAX_BARS
from pine import PineCompileError, PineRuntimeError, compile_source, run
from pine.runner import load_bars

router = APIRouter(tags=["ranking"])

MAX_SCRIPTS = 20


def run_ranking(scripts: list[dict], df, timeframe: str) -> list[dict]:
    """Backtest each script dict ({id, name, source}) on the shared bars.

    Per-script failures are reported in-band — one bad script never aborts
    the batch. Heavy result fields (bars/plots/equity/trades) are discarded;
    only metrics survive.
    """
    items: list[dict] = []
    for s in scripts:
        item = {"script_id": s["id"], "name": s["name"], "ok": False,
                "title": None, "error": None, "metrics": None}
        if s.get("source") is None:
            item["error"] = "script not found"
            items.append(item)
            continue
        try:
            prog = compile_source(s["source"])
        except PineCompileError as e:
            d = e.to_dict()
            item["error"] = f"line {d['line']}:{d['col']} {d['message']}"
            items.append(item)
            continue
        item["title"] = prog.title
        if prog.script_type != "strategy":
            item["error"] = "indicator script — nothing to rank"
            items.append(item)
            continue
        try:
            result = run(prog, df, None, timeframe=timeframe)
        except PineRuntimeError as e:
            d = e.to_dict()
            item["error"] = f"line {d['line']}:{d['col']} {d['message']}"
            items.append(item)
            continue
        item["ok"] = True
        item["metrics"] = result["metrics"]
        items.append(item)
    return items


@router.post("/ranking/run", response_model=RankingResponse)
def ranking_run(req: RankingRequest):
    if not req.script_ids:
        raise HTTPException(status_code=400, detail="script_ids must not be empty")
    if len(req.script_ids) > MAX_SCRIPTS:
        raise HTTPException(status_code=400,
                            detail=f"at most {MAX_SCRIPTS} scripts per ranking run")

    try:
        df = load_bars(req.timeframe, req.start_date, req.end_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if df.empty:
        raise HTTPException(status_code=400, detail="no bars in the requested date range")
    if len(df) > MAX_BARS:
        df = df.tail(MAX_BARS)

    scripts: list[dict] = []
    for sid in req.script_ids:
        try:
            scripts.append(store.get_script(sid))
        except KeyError:
            scripts.append({"id": sid, "name": f"#{sid}", "source": None})

    items = run_ranking(scripts, df, req.timeframe)

    log_event("ranking_run", scripts=len(req.script_ids), timeframe=req.timeframe,
              bars=len(df))
    return RankingResponse(
        timeframe=req.timeframe,
        bars=len(df),
        start=str(df.index.min().date()),
        end=str(df.index.max().date()),
        results=[RankingItem(**it) for it in items],
    )
