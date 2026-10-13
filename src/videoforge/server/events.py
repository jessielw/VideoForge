"""Server -> browser events over one WebSocket: job changes, progress, log lines, queue state.

publish() is called from worker threads; each connected client has an asyncio
queue on the server's event loop. A slow client drops its oldest messages rather
than stalling the workers.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

_CLIENT_BUFFER = 2000


class EventHub:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._clients: set[asyncio.Queue[dict[str, Any]]] = set()
        self._lock = threading.Lock()

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=_CLIENT_BUFFER)
        with self._lock:
            self._clients.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._clients.discard(q)

    def publish(self, kind: str, **data: Any) -> None:
        """Thread-safe; a no-op until the server's loop is bound (e.g. in unit tests)."""
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        event = {"type": kind, **data}
        try:
            loop.call_soon_threadsafe(self._fan_out, event)
        except RuntimeError:  # loop shutting down
            pass

    def _fan_out(self, event: dict[str, Any]) -> None:
        with self._lock:
            clients = list(self._clients)
        for q in clients:
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(event)
