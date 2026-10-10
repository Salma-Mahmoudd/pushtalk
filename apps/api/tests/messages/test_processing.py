import asyncio
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fakeredis import FakeAsyncRedis
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pushtalk.infra.storage import FileStorage
from pushtalk.messages.models import Message, MessageStatus
from pushtalk.messages.processing import ProcessingContext, process_message
from pushtalk.realtime.bus import EventBus
from tests.helpers import create_channel, published_events, signup
from tests.recordings import make_recording, requires_ffmpeg

pytestmark = [pytest.mark.integration, requires_ffmpeg]


@pytest.fixture
def ctx(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    storage: FileStorage,
    fake_redis: FakeAsyncRedis,
) -> ProcessingContext:
    return ProcessingContext(
        sessionmaker=db_sessionmaker, storage=storage, bus=EventBus(fake_redis)
    )


async def _accepted(client: AsyncClient, channel_id: str, path: Path) -> uuid.UUID:
    response = await client.post(
        f"/api/channels/{channel_id}/messages",
        files={"file": (path.name, await asyncio.to_thread(path.read_bytes), "audio/webm")},
        data={"client_msg_id": str(uuid.uuid4())},
    )
    assert response.status_code == 202, response.text
    return uuid.UUID(response.json()["id"])


@pytest.fixture
async def setup(db_client: AsyncClient) -> tuple[dict[str, Any], str]:
    alice = await signup(db_client, "alice")
    channel = await create_channel(db_client, "general")
    return alice, str(channel["id"])


async def test_processing_makes_the_message_ready_and_broadcasts_it(
    db_client: AsyncClient,
    setup: tuple[dict[str, Any], str],
    ctx: ProcessingContext,
    fake_redis: FakeAsyncRedis,
    tmp_path: Path,
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    _, channel_id = setup
    message_id = await _accepted(
        db_client, channel_id, make_recording(tmp_path / "a.webm", 2, streamed=True)
    )

    events = await published_events(
        fake_redis, f"ch:{channel_id}", lambda: process_message(message_id, ctx)
    )

    async with db_sessionmaker() as session:
        message = await session.get(Message, message_id)
    assert message is not None
    assert message.status is MessageStatus.ready
    assert message.seq == 1
    assert message.duration_ms is not None and abs(message.duration_ms - 2000) <= 60
    assert message.waveform is not None and len(message.waveform) == 64
    assert ctx.storage.exists(f"processed/{message_id}.ogg")
    assert not ctx.storage.exists(message.original_key)  # original removed after success
    assert [(e["type"], e["data"]["id"], e["data"]["seq"]) for e in events] == [
        ("message.ready", str(message_id), 1)
    ]


async def test_seq_follows_processing_order(
    db_client: AsyncClient,
    setup: tuple[dict[str, Any], str],
    ctx: ProcessingContext,
    tmp_path: Path,
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    _, channel_id = setup
    first = await _accepted(db_client, channel_id, make_recording(tmp_path / "a.webm", 1))
    second = await _accepted(db_client, channel_id, make_recording(tmp_path / "b.webm", 1))

    await process_message(second, ctx)  # finishes first, so it is heard first
    await process_message(first, ctx)

    async with db_sessionmaker() as session:
        messages = {m: await session.get(Message, m) for m in (first, second)}
    assert {m: message.seq for m, message in messages.items() if message} == {second: 1, first: 2}


async def test_unreadable_audio_fails_and_tells_the_sender(
    db_client: AsyncClient,
    setup: tuple[dict[str, Any], str],
    ctx: ProcessingContext,
    fake_redis: FakeAsyncRedis,
    tmp_path: Path,
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    alice, channel_id = setup
    message_id = await _accepted(db_client, channel_id, make_recording(tmp_path / "a.webm", 1))
    async with db_sessionmaker() as session:
        accepted = await session.get(Message, message_id)
        assert accepted is not None
        original = accepted.original_key
    ctx.storage.path(original).write_bytes(b"\x1a\x45\xdf\xa3 corrupted after upload")

    events = await published_events(
        fake_redis, f"user:{alice['id']}", lambda: process_message(message_id, ctx)
    )

    async with db_sessionmaker() as session:
        message = await session.get(Message, message_id)
    assert message is not None and message.status is MessageStatus.failed
    assert message.failure_reason == "invalid_audio"
    assert message.seq is None
    assert ctx.storage.exists(original)  # kept for debugging
    assert [(e["type"], e["data"]["reason"]) for e in events] == [
        ("message.failed", "invalid_audio")
    ]


async def test_processing_twice_changes_nothing(
    db_client: AsyncClient,
    setup: tuple[dict[str, Any], str],
    ctx: ProcessingContext,
    tmp_path: Path,
    fake_redis: FakeAsyncRedis,
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    _, channel_id = setup
    message_id = await _accepted(db_client, channel_id, make_recording(tmp_path / "a.webm", 1))
    await process_message(message_id, ctx)

    events = await published_events(
        fake_redis, f"ch:{channel_id}", lambda: process_message(message_id, ctx)
    )

    async with db_sessionmaker() as session:
        message = await session.get(Message, message_id)
    assert message is not None and message.seq == 1
    assert events == []


async def test_audio_is_served_to_members_with_range_support(
    db_client: AsyncClient,
    setup: tuple[dict[str, Any], str],
    ctx: ProcessingContext,
    tmp_path: Path,
    make_client: Callable[[], AsyncClient],
) -> None:
    _, channel_id = setup
    message_id = await _accepted(db_client, channel_id, make_recording(tmp_path / "a.webm", 1))
    await process_message(message_id, ctx)
    url = f"/api/messages/{message_id}/audio"

    full = await db_client.get(url)
    partial = await db_client.get(url, headers={"Range": "bytes=0-99"})
    outsider = make_client()
    await signup(outsider, "mallory")
    hidden = await outsider.get(url)

    assert full.status_code == 200
    assert full.headers["content-type"] == "audio/ogg"
    assert full.content.startswith(b"OggS")
    assert partial.status_code == 206
    assert len(partial.content) == 100
    assert hidden.status_code == 404  # not "forbidden": existence is not revealed


async def test_history_lists_ready_messages_in_seq_order(
    db_client: AsyncClient,
    setup: tuple[dict[str, Any], str],
    ctx: ProcessingContext,
    tmp_path: Path,
) -> None:
    _, channel_id = setup
    ids = [
        await _accepted(db_client, channel_id, make_recording(tmp_path / f"{n}.webm", 1))
        for n in range(3)
    ]
    for message_id in ids:
        await process_message(message_id, ctx)
    path = f"/api/channels/{channel_id}/messages"

    newest_two = (await db_client.get(path, params={"limit": 2})).json()
    older = (await db_client.get(path, params={"before_seq": 2})).json()
    after_first = (await db_client.get(path, params={"after_seq": 1})).json()

    assert [m["seq"] for m in newest_two["messages"]] == [2, 3]
    assert newest_two["has_more"] is True
    assert [m["seq"] for m in older["messages"]] == [1]
    assert [m["seq"] for m in after_first["messages"]] == [2, 3]
    assert newest_two["pending"] == []
