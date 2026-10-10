"""WebSocket endpoint for live transactions and alerts.

Authentication happens in the first message ({"token": "<jwt>"}) rather than in the URL:
query strings end up in access logs and proxies, and a login token must never be logged.
Close code 4401 tells the browser its session is invalid so it can log out instead of retrying.
"""
import asyncio

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from ..db.session import SessionLocal
from ..realtime.hub import hub
from .deps import user_from_token

router = APIRouter()
AUTH_TIMEOUT_SECONDS = 5


@router.websocket("/ws")
async def websocket(ws: WebSocket):
    await ws.accept()
    try:
        first = await asyncio.wait_for(ws.receive_json(), timeout=AUTH_TIMEOUT_SECONDS)
        db = SessionLocal()
        try:
            customer_id = user_from_token(str(first.get("token", "")), db).customer_id
        finally:
            db.close()
    except (HTTPException, asyncio.TimeoutError, ValueError, AttributeError, WebSocketDisconnect):
        try:
            await ws.close(code=4401)
        except RuntimeError:  # client already gone
            pass
        return

    hub.connect(customer_id, ws)
    await ws.send_json({"type": "ready"})
    try:
        while True:
            await ws.receive_text()  # we only push; incoming messages are keep-alive pings
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(customer_id, ws)
