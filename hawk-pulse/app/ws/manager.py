"""WebSocket connection manager for real-time alert push."""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages active WebSocket connections.
    Clients subscribe to a domain; alerts are pushed only to relevant subscribers.
    """

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, domain: str) -> None:
        await websocket.accept()
        domain = domain.lower().strip()
        if domain not in self._connections:
            self._connections[domain] = []
        self._connections[domain].append(websocket)
        logger.info("WS connected: %s (total for domain: %d)", domain, len(self._connections[domain]))

    def disconnect(self, websocket: WebSocket, domain: str) -> None:
        domain = domain.lower().strip()
        conns = self._connections.get(domain, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns:
            self._connections.pop(domain, None)
        logger.info("WS disconnected: %s", domain)

    async def broadcast_alert(self, domain: str, alert_data: dict[str, Any]) -> None:
        """Push an alert to all WebSocket clients subscribed to this domain."""
        domain = domain.lower().strip()
        conns = self._connections.get(domain, [])
        if not conns:
            return
        payload = json.dumps(alert_data, default=str)
        stale: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_text(payload)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.disconnect(ws, domain)

    async def broadcast_to_all(self, alert_data: dict[str, Any]) -> None:
        """Push an alert to every connected client regardless of domain."""
        payload = json.dumps(alert_data, default=str)
        for domain, conns in list(self._connections.items()):
            stale: list[WebSocket] = []
            for ws in conns:
                try:
                    await ws.send_text(payload)
                except Exception:
                    stale.append(ws)
            for ws in stale:
                self.disconnect(ws, domain)

    @property
    def active_connections(self) -> int:
        return sum(len(c) for c in self._connections.values())
