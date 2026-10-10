"""WebSocket endpoint for live transactions and alerts.
Browsers can't set headers on WebSocket connections, so the JWT is passed as ?token=."""
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from ..db.session import SessionLocal
from ..realtime.hub import hub
from .deps import user_from_token

router = APIRouter()


@router.websocket("/ws")
async def websocket(ws: WebSocket, token: str = ""):
    db = SessionLocal()
    try:
        customer_id = user_from_token(token, db).customer_id
    except HTTPException:
        await ws.close(code=4401)
        return
    finally:
        db.close()

    await hub.connect(customer_id, ws)
    try:
        while True:
            await ws.receive_text()  # we only push; incoming messages are keep-alive pings
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(customer_id, ws)
