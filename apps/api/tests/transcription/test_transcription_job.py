import asyncio
import uuid
from pathlib import Path
from typing import Any

import pytest
from fakeredis import FakeAsyncRedis
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pushtalk.infra.storage import FileStorage
from pushtalk.messages.models import Message, TranscriptStatus
from pushtalk.messages.processing import ProcessingContext, process_message
from pushtalk.realtime.bus import EventBus
from pushtalk.transcription.job import fail_transcription, transcribe_message
from pushtalk.transcription.transcribers import Transcript
from tests.helpers import create_channel, published_events, signup
from tests.recordings import make_recording, requires_ffmpeg

pytestmark = [pytest.mark.integration, requires_ffmpeg]


class FakeTranscriber:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[Path] = []
        self.fail = fail

    def transcribe(self, audio: Path) -> Transcript:
        self.calls.append(audio)
        if self.fail:
            raise RuntimeError("model crashed")
        return Transcript(text="Testing one two", language="en")


@pytest.fixture
def queued() -> list[uuid.UUID]:
    return []


@pytest.fixture
def ctx(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    storage: FileStorage,
    fake_redis: FakeAsyncRedis,
    queued: list[uuid.UUID],
) -> ProcessingContext:
    async def enqueue(message_id: uuid.UUID) -> None:
        queued.append(message_id)

    return ProcessingContext(
        sessionmaker=db_sessionmaker,
        storage=storage,
        bus=EventBus(fake_redis),
        enqueue_transcription=enqueue,
    )


async def _ready_message(
    client: AsyncClient, ctx: ProcessingContext, tmp_path: Path
) -> tuple[uuid.UUID, str]:
    await signup(client, "alice")
    channel_id = str((await create_channel(client, "general"))["id"])
    path = make_recording(tmp_path / "hello.webm", 1)
    response = await client.post(
        f"/api/channels/{channel_id}/messages",
        files={"file": (path.name, await asyncio.to_thread(path.read_bytes), "audio/webm")},
        data={"client_msg_id": str(uuid.uuid4())},
    )
    message_id = uuid.UUID(response.json()["id"])
    await process_message(message_id, ctx)
    return message_id, channel_id


async def _message(ctx: ProcessingContext, message_id: uuid.UUID) -> Message:
    async with ctx.sessionmaker() as session:
        message = await session.get(Message, message_id)
    assert message is not None
    return message


async def test_ready_messages_are_queued_for_transcription_after_the_broadcast(
    db_client: AsyncClient,
    ctx: ProcessingContext,
    fake_redis: FakeAsyncRedis,
    queued: list[uuid.UUID],
    tmp_path: Path,
) -> None:
    await signup(db_client, "alice")
    channel_id = str((await create_channel(db_client, "general"))["id"])
    path = make_recording(tmp_path / "hello.webm", 1)
    response = await db_client.post(
        f"/api/channels/{channel_id}/messages",
        files={"file": (path.name, await asyncio.to_thread(path.read_bytes), "audio/webm")},
        data={"client_msg_id": str(uuid.uuid4())},
    )
    message_id = uuid.UUID(response.json()["id"])

    events = await published_events(
        fake_redis, f"ch:{channel_id}", lambda: process_message(message_id, ctx)
    )

    assert events[0]["type"] == "message.ready"
    assert events[0]["data"]["transcript_status"] == "pending"
    assert queued == [message_id]


async def test_transcript_is_saved_and_announced_once(
    db_client: AsyncClient, ctx: ProcessingContext, fake_redis: FakeAsyncRedis, tmp_path: Path
) -> None:
    message_id, channel_id = await _ready_message(db_client, ctx, tmp_path)
    transcriber = FakeTranscriber()

    async def run_twice() -> None:
        await transcribe_message(message_id, ctx, transcriber)
        await transcribe_message(message_id, ctx, transcriber)

    events = await published_events(fake_redis, f"ch:{channel_id}", run_twice)

    assert len(transcriber.calls) == 1
    assert transcriber.calls[0].suffix == ".ogg"  # The processed file, not the upload.
    assert events == [
        {
            "type": "message.transcribed",
            "data": {
                "id": str(message_id),
                "channel_id": channel_id,
                "transcript_status": "done",
                "transcript": "Testing one two",
                "transcript_lang": "en",
            },
        }
    ]
    history = (await db_client.get(f"/api/channels/{channel_id}/messages")).json()["messages"]
    assert (history[0]["transcript_status"], history[0]["transcript"]) == (
        "done",
        "Testing one two",
    )


async def test_a_crash_is_left_to_the_task_retries_then_marked_failed(
    db_client: AsyncClient, ctx: ProcessingContext, fake_redis: FakeAsyncRedis, tmp_path: Path
) -> None:
    message_id, channel_id = await _ready_message(db_client, ctx, tmp_path)

    with pytest.raises(RuntimeError):
        await transcribe_message(message_id, ctx, FakeTranscriber(fail=True))
    assert (await _message(ctx, message_id)).transcript_status is TranscriptStatus.pending

    events = await published_events(
        fake_redis, f"ch:{channel_id}", lambda: fail_transcription(message_id, ctx)
    )

    assert (await _message(ctx, message_id)).transcript_status is TranscriptStatus.failed
    assert events[0]["data"]["transcript_status"] == "failed"


async def test_a_queue_failure_marks_the_transcript_failed_not_the_message(
    db_client: AsyncClient, ctx: ProcessingContext, tmp_path: Path
) -> None:
    async def broker_down(_: uuid.UUID) -> None:
        raise ConnectionError("broker unavailable")

    broken = ProcessingContext(
        sessionmaker=ctx.sessionmaker,
        storage=ctx.storage,
        bus=ctx.bus,
        enqueue_transcription=broker_down,
    )
    message_id, _ = await _ready_message(db_client, broken, tmp_path)

    message = await _message(ctx, message_id)
    assert (message.status.value, message.transcript_status) == ("ready", TranscriptStatus.failed)


async def test_no_transcript_when_transcription_is_off(
    db_client: AsyncClient, ctx: ProcessingContext, tmp_path: Path
) -> None:
    off = ProcessingContext(sessionmaker=ctx.sessionmaker, storage=ctx.storage, bus=ctx.bus)
    message_id, _ = await _ready_message(db_client, off, tmp_path)
    message: Any = await _message(ctx, message_id)

    assert message.transcript_status is None
    await transcribe_message(message_id, ctx, FakeTranscriber())  # A stray job does nothing.
    assert (await _message(ctx, message_id)).transcript_status is None
