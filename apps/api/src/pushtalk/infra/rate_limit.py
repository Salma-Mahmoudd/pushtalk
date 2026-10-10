import math
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus

from redis.asyncio import Redis

from pushtalk.core.errors import AppError

# Sliding window in one atomic step: drop attempts older than the window, then record this
# attempt only if there is room. Rejected attempts are not recorded, so waiting always helps.
# Returns 0 when allowed, otherwise the milliseconds until the oldest attempt leaves the window.
_SLIDING_WINDOW = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
if redis.call('ZCARD', key) < limit then
  redis.call('ZADD', key, now, ARGV[4])
  redis.call('PEXPIRE', key, window)
  return 0
end
local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
return tonumber(oldest[2]) + window - now
"""


@dataclass(frozen=True)
class RateLimitRule:
    scope: str
    limit: int
    window_s: int

    @classmethod
    def parse(cls, scope: str, value: str) -> "RateLimitRule":
        """Builds a rule from "<requests>/<seconds>", e.g. "10/900"."""
        requests, _, seconds = value.partition("/")
        rule = cls(scope=scope, limit=int(requests), window_s=int(seconds))
        if rule.limit < 1 or rule.window_s < 1:
            raise ValueError(f"invalid rate limit {value!r}")
        return rule


class RateLimited(AppError):
    status_code = HTTPStatus.TOO_MANY_REQUESTS
    code = "rate_limited"

    def __init__(self, retry_after_s: int) -> None:
        super().__init__(
            f"Too many requests. Try again in {retry_after_s} s.",
            headers={"Retry-After": str(retry_after_s)},
        )
        self.retry_after_s = retry_after_s


class RateLimiter:
    def __init__(self, redis: Redis, clock: Callable[[], float] = time.time) -> None:
        self._script = redis.register_script(_SLIDING_WINDOW)
        self._clock = clock

    async def hit(self, rule: RateLimitRule, key: str) -> None:
        """Counts one attempt for `key` (a user id, username or IP); raises RateLimited if over."""
        wait_ms = await self._script(
            keys=[f"ratelimit:{rule.scope}:{key}"],
            args=[int(self._clock() * 1000), rule.window_s * 1000, rule.limit, uuid.uuid4().hex],
        )
        if int(wait_ms) > 0:
            raise RateLimited(retry_after_s=max(1, math.ceil(int(wait_ms) / 1000)))
