"""EventBus: stamps the contract envelope and fans events out to subscribers.

One bus per session. Subscribers are async queues (one per websocket client).
A bounded replay buffer lets a client that connects mid-session catch up.
"""
from __future__ import annotations
import asyncio, time
from typing import Any, AsyncIterator


class EventBus:
    def __init__(self, replay_size: int = 500) -> None:
        self._seq = 0
        self._subs: set[asyncio.Queue[dict[str, Any]]] = set()
        self._replay: list[dict[str, Any]] = []
        self._replay_size = replay_size

    @property
    def seq(self) -> int:
        return self._seq

    def stamp(self, event: dict[str, Any]) -> dict[str, Any]:
        self._seq += 1
        return {"v": 1, "seq": self._seq, "ts": round(time.time(), 3), **event}

    async def emit(self, event: dict[str, Any]) -> dict[str, Any]:
        """Stamp and broadcast. Returns the stamped event."""
        stamped = self.stamp(event)
        self._replay.append(stamped)
        if len(self._replay) > self._replay_size:
            del self._replay[: len(self._replay) - self._replay_size]
        for q in list(self._subs):
            try:
                q.put_nowait(stamped)
            except asyncio.QueueFull:
                # Slow client: drop it rather than stall the agent.
                self._subs.discard(q)
        return stamped

    def history(self) -> list[dict[str, Any]]:
        return list(self._replay)

    async def subscribe(self, replay: bool = True) -> AsyncIterator[dict[str, Any]]:
        """Yield events until the consumer stops iterating."""
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)
        if replay:
            for e in self._replay:
                q.put_nowait(e)
        self._subs.add(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._subs.discard(q)

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)
