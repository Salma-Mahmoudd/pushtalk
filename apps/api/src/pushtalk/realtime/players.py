import uuid

from redis.asyncio import Redis

from pushtalk.realtime.bus import EventBus, event, user_topic

_TTL_S = 24 * 3600


def _key(channel_id: uuid.UUID, user_id: uuid.UUID) -> str:
    return f"player:{channel_id}:{user_id}"


class PlayerRegistry:
    """Which of a user's connections plays a channel's audio (DECISIONS.md, 1.4).

    Only connections open on the channel can play; the one claimed most recently (focused last)
    does. Every connection of the user hears about each change and goes quiet if it lost.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._bus = EventBus(redis)

    async def claim(self, channel_id: uuid.UUID, user_id: uuid.UUID, conn_id: uuid.UUID) -> None:
        await self._redis.set(_key(channel_id, user_id), str(conn_id), ex=_TTL_S)
        await self._announce(channel_id, user_id, conn_id)

    async def claim_if_free(
        self, channel_id: uuid.UUID, user_id: uuid.UUID, conn_id: uuid.UUID
    ) -> None:
        """The first connection plays until another one claims."""
        if await self._redis.set(_key(channel_id, user_id), str(conn_id), ex=_TTL_S, nx=True):
            await self._announce(channel_id, user_id, conn_id)

    async def active(self, channel_id: uuid.UUID, user_id: uuid.UUID) -> str | None:
        value = await self._redis.get(_key(channel_id, user_id))
        return None if value is None else str(value)

    async def release(self, channel_id: uuid.UUID, user_id: uuid.UUID, conn_id: uuid.UUID) -> None:
        """When the playing connection closes, the user's other connections may claim."""
        if await self.active(channel_id, user_id) == str(conn_id):
            await self._redis.delete(_key(channel_id, user_id))
            await self._announce(channel_id, user_id, None)

    async def _announce(
        self, channel_id: uuid.UUID, user_id: uuid.UUID, conn_id: uuid.UUID | None
    ) -> None:
        await self._bus.publish(
            user_topic(user_id),
            event(
                "playback.claimed",
                channel_id=str(channel_id),
                connection_id=None if conn_id is None else str(conn_id),
            ),
        )
