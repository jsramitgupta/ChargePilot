import asyncio
import json
from typing import Dict, Any

# Simple in-process broadcaster for Server-Sent Events (SSE).
# Each client registers and receives a personal asyncio.Queue that the
# server publishes JSON-serializable dicts to via `publish_event`.

_clients: list[asyncio.Queue] = []


def register_client() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _clients.append(q)

    return q


def unregister_client(q: asyncio.Queue) -> None:
    try:
        _clients.remove(q)
    except ValueError:
        pass


def publish_event(event: Dict[str, Any]) -> None:
    # fire-and-forget push to all queues (non-blocking)
    data = event.copy()
    for q in list(_clients):
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            # skip slow clients
            pass
