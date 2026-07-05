"""Pine Script endpoints — validate and backtest on XAUUSD."""
from fastapi import APIRouter, HTTPException

from api.logger import log_event
from api.schemas import (PineBacktestRequest, PineBacktestResponse, PineSource,
                         PineValidateResponse)
from pine import PineCompileError, PineRuntimeError, compile_source, run
from pine.runner import load_bars

router = APIRouter(tags=["pine"])

# Guard against accidentally huge runs — M15 full history is ~150k bars,
# the bar-by-bar interpreter handles ~10-20k bars/s.
MAX_BARS = 200_000


@router.post("/pine/validate", response_model=PineValidateResponse)
def validate(req: PineSource):
    try:
        prog = compile_source(req.source)
    except PineCompileError as e:
        return PineValidateResponse(ok=False, errors=[e.to_dict()])
    return PineValidateResponse(ok=True, script_type=prog.script_type, title=prog.title)


@router.post("/pine/backtest", response_model=PineBacktestResponse)
def backtest(req: PineBacktestRequest):
    try:
        prog = compile_source(req.source)
    except PineCompileError as e:
        return PineBacktestResponse(ok=False, errors=[e.to_dict()])

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

    overrides = req.settings.model_dump() if req.settings else None
    try:
        result = run(prog, df, overrides, timeframe=req.timeframe)
    except PineRuntimeError as e:
        return PineBacktestResponse(ok=False, script_type=prog.script_type,
                                    title=prog.title, errors=[e.to_dict()])

    log_event("pine_backtest", script_type=prog.script_type, title=prog.title,
              timeframe=req.timeframe, bars=len(df),
              trades=len(result["trades"]))
    return PineBacktestResponse(**result)
