import asyncio
import logging
import random

from psycopg import AsyncConnection
from starlette.websockets import WebSocket, WebSocketDisconnect

from app.core.config import settings

logger = logging.getLogger("chargepilot.connector_notifications")
NOTIFICATION_CHANNEL = "chargepilot_connector_commands"


class ConnectorWebSocketManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._send_locks: dict[WebSocket, asyncio.Lock] = {}
        self._lock = asyncio.Lock()

    async def connect(self, connector_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.setdefault(connector_id, set()).add(websocket)
            self._send_locks.setdefault(websocket, asyncio.Lock())

    async def disconnect(self, connector_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self._connections.get(connector_id)
            if connections is None:
                return
            connections.discard(websocket)
            self._send_locks.pop(websocket, None)
            if not connections:
                self._connections.pop(connector_id, None)

    async def send(self, websocket: WebSocket, message: dict[str, str]) -> None:
        async with self._lock:
            send_lock = self._send_locks.get(websocket)
        if send_lock is None:
            return
        async with send_lock:
            await websocket.send_json(message)

    async def publish(self, connector_id: str) -> None:
        async with self._lock:
            connections = tuple(self._connections.get(connector_id, ()))

        stale_connections = []
        for websocket in connections:
            try:
                await asyncio.wait_for(
                    self.send(websocket, {"type": "commands_available"}),
                    timeout=5,
                )
            except (TimeoutError, RuntimeError, WebSocketDisconnect):
                stale_connections.append(websocket)
            except Exception as exc:
                logger.warning(
                    "Could not notify connector websocket (%s).",
                    type(exc).__name__,
                )
                stale_connections.append(websocket)

        for websocket in stale_connections:
            await self.disconnect(connector_id, websocket)


connector_websockets = ConnectorWebSocketManager()


async def listen_for_connector_notifications() -> None:
    if not settings.database_url.startswith("postgresql+psycopg://"):
        return

    dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    retry_delay = 1.0
    while True:
        try:
            async with await AsyncConnection.connect(dsn, autocommit=True) as connection:
                await connection.execute(f"LISTEN {NOTIFICATION_CHANNEL}")
                logger.info("Listening for committed connector command notifications.")
                retry_delay = 1.0
                async for notification in connection.notifies(timeout=30, stop_after=1):
                    await connector_websockets.publish(notification.payload)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "Connector command notification listener disconnected (%s).",
                type(exc).__name__,
            )
            await asyncio.sleep(random.uniform(retry_delay / 2, retry_delay))
            retry_delay = min(retry_delay * 2, 30)
