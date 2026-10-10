import asyncio

import structlog
from redis.asyncio import Redis

from pushtalk.channels.presence import PresenceService
from pushtalk.realtime.bus import EventBus, channel_topic, event

log = structlog.get_logger(__name__)

SWEEP_INTERVAL_S = 30
_LOCK_KEY = "lock:presence-sweep"


async def sweep_presence_forever(redis: Redis, presence: PresenceService) -> None:
    """Announces users whose connections stopped sending heartbeats (closed tab, crash).

    Every API process runs this; a short Redis lock lets one of them sweep per interval.
    """
    bus = EventBus(redis)
    while True:
        await asyncio.sleep(SWEEP_INTERVAL_S)
        try:
            if not await redis.set(_LOCK_KEY, "1", nx=True, ex=SWEEP_INTERVAL_S - 5):
                continue
            for channel_id, user_id in await presence.sweep():
                await bus.publish(
                    channel_topic(channel_id),
                    event("presence.update", user_id=str(user_id), online=False),
                )
        except Exception as exc:  # Redis briefly unavailable: try again next interval.
            log.warning("presence.sweep_failed", error_type=type(exc).__name__)
