import pytest
from fakeredis import FakeAsyncRedis

from pushtalk.infra.rate_limit import LocalRateLimiter, RateLimited, RateLimiter, RateLimitRule

RULE = RateLimitRule(scope="test", limit=3, window_s=60)


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def limiter(clock: Clock) -> RateLimiter:
    return RateLimiter(FakeAsyncRedis(), clock=clock)


async def test_allows_up_to_the_limit(limiter: RateLimiter) -> None:
    for _ in range(RULE.limit):
        await limiter.hit(RULE, "alice")


async def test_refuses_over_the_limit_with_retry_after(limiter: RateLimiter, clock: Clock) -> None:
    for _ in range(RULE.limit):
        await limiter.hit(RULE, "alice")
        clock.now += 10

    with pytest.raises(RateLimited) as refused:
        await limiter.hit(RULE, "alice")

    # The first attempt (30 s ago) leaves the 60 s window in 30 s.
    assert refused.value.retry_after_s == 30
    assert refused.value.headers == {"Retry-After": "30"}
    assert refused.value.status_code == 429


async def test_window_slides(limiter: RateLimiter, clock: Clock) -> None:
    for _ in range(RULE.limit):
        await limiter.hit(RULE, "alice")
    clock.now += RULE.window_s + 1

    await limiter.hit(RULE, "alice")


async def test_refused_attempts_do_not_extend_the_block(limiter: RateLimiter, clock: Clock) -> None:
    for _ in range(RULE.limit):
        await limiter.hit(RULE, "alice")
    for _ in range(5):
        with pytest.raises(RateLimited):
            await limiter.hit(RULE, "alice")
    clock.now += RULE.window_s + 1

    await limiter.hit(RULE, "alice")


async def test_keys_are_independent(limiter: RateLimiter) -> None:
    for _ in range(RULE.limit):
        await limiter.hit(RULE, "alice")

    await limiter.hit(RULE, "bob")


def test_rule_parse() -> None:
    assert RateLimitRule.parse("login", "10/900") == RateLimitRule("login", 10, 900)
    with pytest.raises(ValueError):
        RateLimitRule.parse("login", "0/900")


def test_local_limiter_slides_its_window(clock: Clock) -> None:
    local = LocalRateLimiter(RateLimitRule(scope="ws", limit=2, window_s=1), clock=clock)

    assert [local.allow(), local.allow(), local.allow()] == [True, True, False]
    clock.now += 1
    assert local.allow()
