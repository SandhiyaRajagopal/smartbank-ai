"""WebSocket hub: keeps each logged-in customer's open browser connections and pushes
events (new transaction, fraud alert, balance change) to them in real time.

Why WebSockets? HTTP is request -> response; the browser would have to poll. A WebSocket
stays open so the server can push a fraud alert the moment the transaction is scored.
"""
import asyncio
import logging
from collections import defaultdict

from fastapi import WebSocket

log = logging.getLogger("smartbank.ws")


class Hub:
    def __init__(self) -> None:
        self.connections: dict[int, set[WebSocket]] = defaultdict(set)
        self.loop: asyncio.AbstractEventLoop | None = None

    def connect(self, customer_id: int, ws: WebSocket) -> None:
        """Register an already-accepted, authenticated connection."""
        self.connections[customer_id].add(ws)

    def disconnect(self, customer_id: int, ws: WebSocket) -> None:
        self.connections[customer_id].discard(ws)

    async def publish(self, customer_id: int, event: dict) -> None:
        for ws in list(self.connections.get(customer_id, ())):
            try:
                await ws.send_json(event)
            except Exception:
                self.disconnect(customer_id, ws)

    def publish_threadsafe(self, customer_id: int, event: dict) -> None:
        """For code running in worker threads (e.g. a sync API endpoint)."""
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.publish(customer_id, event), self.loop)

    def online_customers(self) -> list[int]:
        return [cid for cid, conns in self.connections.items() if conns]


hub = Hub()
