"""XAUUSD chart data — the only instrument this platform serves."""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

import config
from api.sync import read_marker
from pine.runner import load_bars

router = APIRouter(tags=["chart"])


@router.get("/chart/info")
def chart_info():
    """Available timeframes and their bar counts / date ranges."""
    marker = read_marker()
    out = {
        "symbol": config.SYMBOL,
        "last_synced": marker.get("last_synced") if marker else None,
        "timeframes": {},
    }
    for tf, fname in config.TF_TO_FILE.items():
        path = config.DATA_DIR / fname
        if not path.exists():
            continue
        try:
            df = load_bars(tf)
        except Exception:
            continue
        out["timeframes"][tf] = {
            "bars": len(df),
            "start": str(df.index.min().date()) if len(df) else None,
            "end": str(df.index.max().date()) if len(df) else None,
            "last_modified": datetime.fromtimestamp(
                path.stat().st_mtime, tz=timezone.utc).isoformat(),
        }
    return out


@router.get("/chart/data")
def chart_data(
    tf: str = Query("H1", description="Timeframe key: M15 | H1 | H4"),
    limit: int = Query(2000, ge=10, le=50000),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
):
    try:
        df = load_bars(tf, start_date, end_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    df = df.tail(limit)
    bars = [{"time": int(t.timestamp()), "open": float(r["open"]),
             "high": float(r["high"]), "low": float(r["low"]),
             "close": float(r["close"])}
            for t, r in df.iterrows()]
    return {"symbol": config.SYMBOL, "tf": tf, "bars": bars}
