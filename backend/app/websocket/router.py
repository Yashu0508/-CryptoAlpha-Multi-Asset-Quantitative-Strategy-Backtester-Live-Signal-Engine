"""WebSocket endpoint definitions."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.websocket.manager import ConnectionManager

router = APIRouter()
manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Maintain a basic connection; market-data messaging is intentionally deferred."""

    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
