import asyncio
import contextlib
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

import structlog
from fastapi import WebSocket
from redis.asyncio import Redis
from redis.asyncio.client import PubSub

from pushtalk.realtime.bus import Event

log = structlog.get_logger(__name__)

# Close code for a missing, expired or revoked session: the client refreshes, then reconnects.
CLOSE_UNAUTHORIZED = 4401


@dataclass(eq=False)
class Connection:
    websocket: WebSocket
    user_id: uuid.UUID
    session_id: uuid.UUID
    id: uuid.UUID = field(default_factory=uuid.uuid4)

    async def send(self, payload: Event) -> None:
        await self.websocket.send_json(payload)


class ConnectionManager:
    """Sockets of this API process, and the Redis subscriptions that feed them.

    Each topic is subscribed once per process, however many local sockets listen to it, and
    unsubscribed when the last one leaves.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._pubsub: PubSub | None = None
        self._listeners: dict[str, set[Connection]] = defaultdict(set)
        self._topics: dict[Connection, list[str]] = {}
        self._lock = asyncio.Lock()
        self._reader: asyncio.Task[None] | None = None

    async def register(self, connection: Connection, topics: list[str]) -> None:
        async with self._lock:
            if self._pubsub is None:
                self._pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
            new_topics = [topic for topic in topics if not self._listeners[topic]]
            for topic in topics:
                self._listeners[topic].add(connection)
            self._topics[connection] = topics
            if new_topics:
                await self._pubsub.subscribe(*new_topics)
            if self._reader is None or self._reader.done():
                self._reader = asyncio.create_task(self._read(), name="realtime-reader")

    async def unregister(self, connection: Connection) -> None:
        async with self._lock:
            unused = []
            for topic in self._topics.pop(connection, []):
                self._listeners[topic].discard(connection)
                if not self._listeners[topic]:
                    del self._listeners[topic]
                    unused.append(topic)
            if unused and self._pubsub is not None:
                await self._pubsub.unsubscribe(*unused)

    async def close(self) -> None:
        if self._reader is not None:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader
        if self._pubsub is not None:
            await self._pubsub.aclose()  # type: ignore[no-untyped-call]  # untyped in redis-py

    async def _read(self) -> None:
        assert self._pubsub is not None
        while True:
            try:
                message = await self._pubsub.get_message(timeout=1.0)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # Redis restarting: the pub/sub client resubscribes itself.
                log.warning("realtime.pubsub_error", error_type=type(exc).__name__)
                await asyncio.sleep(1)
                continue
            if message is None or message["type"] != "message":
                continue
            await self._deliver(message["channel"], json.loads(message["data"]))

    async def _deliver(self, topic: str, payload: Event) -> None:
        listeners = list(self._listeners.get(topic, ()))
        if payload.get("type") == "session.revoked":
            session_id = uuid.UUID(payload["data"]["session_id"])
            await asyncio.gather(
                *(
                    connection.websocket.close(code=CLOSE_UNAUTHORIZED)
                    for connection in listeners
                    if connection.session_id == session_id
                ),
                return_exceptions=True,
            )
            return
        # A socket that is closing or slow must not hold up the others.
        await asyncio.gather(
            *(connection.send(payload) for connection in listeners), return_exceptions=True
        )
