import json
import uuid
from typing import Any

from redis.asyncio import Redis

Event = dict[str, Any]


def event(type_: str, **data: Any) -> Event:
    """The WebSocket event envelope: {"type": ..., "data": {...}}."""
    return {"type": type_, "data": data}


def channel_topic(channel_id: uuid.UUID) -> str:
    return f"ch:{channel_id}"


def user_topic(user_id: uuid.UUID) -> str:
    return f"user:{user_id}"


class EventBus:
    """Redis pub/sub: every API process receives every event and forwards it to its sockets."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def publish(self, topic: str, payload: Event) -> None:
        await self._redis.publish(topic, json.dumps(payload, default=str))
