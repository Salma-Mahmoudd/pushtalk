import uuid

import pytest
from fakeredis import FakeAsyncRedis

from pushtalk.channels.presence import PresenceService

CHANNEL = uuid.uuid4()
ALICE = uuid.uuid4()


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def presence(clock: Clock) -> PresenceService:
    return PresenceService(FakeAsyncRedis(decode_responses=True), ttl_s=60, clock=clock)


async def test_first_connection_brings_user_online(presence: PresenceService) -> None:
    assert await presence.connect(CHANNEL, ALICE, uuid.uuid4()) is True
    assert await presence.online(CHANNEL) == {ALICE}


async def test_second_tab_keeps_user_online_until_last_closes(presence: PresenceService) -> None:
    tab_1, tab_2 = uuid.uuid4(), uuid.uuid4()
    await presence.connect(CHANNEL, ALICE, tab_1)

    assert await presence.connect(CHANNEL, ALICE, tab_2) is False  # already online
    assert await presence.disconnect(CHANNEL, ALICE, tab_1) is False  # tab 2 still open
    assert await presence.disconnect(CHANNEL, ALICE, tab_2) is True


async def test_missed_heartbeats_expire(presence: PresenceService, clock: Clock) -> None:
    await presence.connect(CHANNEL, ALICE, uuid.uuid4())
    clock.now += 61

    assert await presence.online(CHANNEL) == set()


async def test_heartbeat_keeps_connection_fresh(presence: PresenceService, clock: Clock) -> None:
    conn = uuid.uuid4()
    await presence.connect(CHANNEL, ALICE, conn)
    clock.now += 50
    await presence.heartbeat(CHANNEL, ALICE, conn)
    clock.now += 50

    assert await presence.online(CHANNEL) == {ALICE}


async def test_sweep_reports_users_that_went_offline(
    presence: PresenceService, clock: Clock
) -> None:
    bob = uuid.uuid4()
    await presence.connect(CHANNEL, ALICE, uuid.uuid4())  # will crash
    clock.now += 50
    await presence.connect(CHANNEL, bob, uuid.uuid4())  # recent
    clock.now += 20

    assert await presence.sweep() == [(CHANNEL, ALICE)]
    assert await presence.sweep() == []  # already swept
    assert await presence.online(CHANNEL) == {bob}
