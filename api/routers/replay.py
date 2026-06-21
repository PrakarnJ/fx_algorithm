import asyncio

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from api.replay_engine import create_session, get_session, delete_session, list_sessions
from api.schemas import ReplayStartRequest, ReplayStartResponse

router = APIRouter(tags=["replay"])


@router.post("/replay/start", response_model=ReplayStartResponse)
async def start_replay(req: ReplayStartRequest):
    session = await create_session(req.algo_name, req.symbol, req.start_date, req.end_date)
    if session._error:
        raise HTTPException(status_code=400, detail=session._error)
    return ReplayStartResponse(
        session_id=session.session_id,
        total_bars=session.total_bars,
        algo_name=session.algo_name,
        symbol=session.symbol,
        exec_tf=session.exec_tf,
        start_date=session.start_date,
        end_date=session.end_date,
    )


@router.get("/replay/sessions")
def get_sessions():
    return {"session_ids": list_sessions()}


@router.delete("/replay/sessions/{session_id}")
def remove_session(session_id: str):
    delete_session(session_id)
    return {"deleted": session_id}


@router.websocket("/ws/replay/{session_id}")
async def replay_ws(websocket: WebSocket, session_id: str):
    await websocket.accept()
    session = get_session(session_id)
    if session is None:
        await websocket.send_json({"type": "error", "message": "Session not found"})
        await websocket.close()
        return

    action_queue: asyncio.Queue = asyncio.Queue()

    async def receive_loop():
        try:
            while True:
                data = await websocket.receive_json()
                await action_queue.put(data)
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    receive_task = asyncio.create_task(receive_loop())
    try:
        await session.stream(websocket, action_queue)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        receive_task.cancel()
