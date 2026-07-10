"""Minimal in-memory WebSocket connection manager.

This process-local manager is suitable for the initial application skeleton. Replace it
with a shared broker-backed implementation before running multiple API replicas.
"""

from fastapi import WebSocket


class ConnectionManager:
    """Own active WebSocket connections for a single application process."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new connection."""

        await websocket.accept()
        self._connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove an inactive connection."""

        self._connections.discard(websocket)

    async def send_text(self, websocket: WebSocket, message: str) -> None:
        """Send a text message to one client."""

        await websocket.send_text(message)
