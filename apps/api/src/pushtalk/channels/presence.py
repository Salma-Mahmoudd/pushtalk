import time
import uuid
from collections.abc import Callable, Sequence

from redis.asyncio import Redis


def _key(channel_id: uuid.UUID) -> str:
    return f"presence:{channel_id}"


def _user_ids(members: Sequence[object]) -> set[uuid.UUID]:
    """Entries are "<user id>:<connection id>"; the client decodes responses to str."""
    return {uuid.UUID(str(member).split(":", 1)[0]) for member in members}


class PresenceService:
    """Who is online per channel: one entry per open connection, scored by its last heartbeat.

    A user is online while at least one of their connections has a fresh heartbeat, so a
    second tab keeps them online and a crashed process's entries simply expire.
    """

    def __init__(
        self, redis: Redis, ttl_s: int = 60, clock: Callable[[], float] = time.time
    ) -> None:
        self._redis = redis
        self._ttl_s = ttl_s
        self._clock = clock

    async def connect(self, channel_id: uuid.UUID, user_id: uuid.UUID, conn_id: uuid.UUID) -> bool:
        """Records a connection; True if the user just came online in this channel."""
        was_online = user_id in await self.online(channel_id)
        await self.heartbeat(channel_id, user_id, conn_id)
        return not was_online

    async def heartbeat(
        self, channel_id: uuid.UUID, user_id: uuid.UUID, conn_id: uuid.UUID
    ) -> None:
        await self._redis.zadd(_key(channel_id), {f"{user_id}:{conn_id}": self._clock()})

    async def disconnect(
        self, channel_id: uuid.UUID, user_id: uuid.UUID, conn_id: uuid.UUID
    ) -> bool:
        """Removes a connection; True if the user is now offline in this channel."""
        await self._redis.zrem(_key(channel_id), f"{user_id}:{conn_id}")
        return user_id not in await self.online(channel_id)

    async def online(self, channel_id: uuid.UUID) -> set[uuid.UUID]:
        fresh = await self._redis.zrangebyscore(
            _key(channel_id), self._clock() - self._ttl_s, "+inf"
        )
        return _user_ids(fresh)

    async def sweep(self) -> list[tuple[uuid.UUID, uuid.UUID]]:
        """Drops expired entries everywhere; returns (channel, user) pairs that went offline."""
        cutoff = self._clock() - self._ttl_s
        went_offline: list[tuple[uuid.UUID, uuid.UUID]] = []
        async for key in self._redis.scan_iter(match="presence:*"):
            stale = await self._redis.zrangebyscore(key, "-inf", cutoff)
            if not stale:
                continue
            await self._redis.zremrangebyscore(key, "-inf", cutoff)
            channel_id = uuid.UUID(str(key).split(":", 1)[1])
            still_online = await self.online(channel_id)
            for user_id in _user_ids(stale):
                if user_id not in still_online:
                    went_offline.append((channel_id, user_id))
        return went_offline
