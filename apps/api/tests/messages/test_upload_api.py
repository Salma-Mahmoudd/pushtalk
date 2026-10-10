import asyncio
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from pushtalk.infra.storage import FileStorage
from tests.helpers import create_channel, signup
from tests.recordings import make_recording, requires_ffmpeg

pytestmark = [pytest.mark.integration, requires_ffmpeg]


async def _upload(
    client: AsyncClient,
    channel_id: str,
    path: Path,
    *,
    client_msg_id: str | None = None,
    content_type: str = "audio/webm",
) -> tuple[int, dict[str, Any]]:
    response = await client.post(
        f"/api/channels/{channel_id}/messages",
        files={"file": (path.name, await asyncio.to_thread(path.read_bytes), content_type)},
        data={"client_msg_id": client_msg_id or str(uuid.uuid4())},
    )
    return response.status_code, response.json()


@pytest.fixture
async def channel_id(db_client: AsyncClient) -> str:
    await signup(db_client, "alice")
    return str((await create_channel(db_client, "general"))["id"])


async def test_valid_recording_is_accepted_and_queued(
    db_client: AsyncClient,
    channel_id: str,
    tmp_path: Path,
    enqueued: list[uuid.UUID],
    storage: FileStorage,
) -> None:
    status, body = await _upload(
        db_client, channel_id, make_recording(tmp_path / "r.webm", 2, streamed=True)
    )

    assert status == 202
    assert body["status"] == "processing"
    assert body["seq"] is None
    assert body["sender"]["username"] == "alice"
    assert enqueued == [uuid.UUID(body["id"])]
    assert len(list((storage.root / "originals").iterdir())) == 1


async def test_retried_upload_returns_the_same_message(
    db_client: AsyncClient, channel_id: str, tmp_path: Path, enqueued: list[uuid.UUID]
) -> None:
    recording = make_recording(tmp_path / "r.webm", 1)
    client_msg_id = str(uuid.uuid4())

    _, first = await _upload(db_client, channel_id, recording, client_msg_id=client_msg_id)
    status, second = await _upload(db_client, channel_id, recording, client_msg_id=client_msg_id)

    assert status == 202
    assert second["id"] == first["id"]
    assert len(enqueued) == 1


async def test_oversized_upload_is_413(
    db_client: AsyncClient, db_app: FastAPI, channel_id: str, tmp_path: Path
) -> None:
    db_app.state.settings = db_app.state.settings.model_copy(update={"max_upload_bytes": 1000})

    status, body = await _upload(db_client, channel_id, make_recording(tmp_path / "r.webm", 2))

    assert status == 413
    assert body["error"]["code"] == "payload_too_large"


async def test_renamed_text_file_is_415_whatever_the_content_type(
    db_client: AsyncClient, channel_id: str, tmp_path: Path
) -> None:
    fake = tmp_path / "voice.webm"
    fake.write_text("<script>alert(1)</script> definitely audio")

    status, body = await _upload(db_client, channel_id, fake, content_type="audio/webm")

    assert status == 415
    assert body["error"]["code"] == "unsupported_media_type"


@pytest.mark.parametrize("seconds", [0.3, 61])
async def test_too_short_or_too_long_is_422(
    db_client: AsyncClient,
    channel_id: str,
    tmp_path: Path,
    seconds: float,
    enqueued: list[uuid.UUID],
) -> None:
    status, body = await _upload(
        db_client, channel_id, make_recording(tmp_path / "r.webm", seconds, streamed=True)
    )

    assert status == 422
    assert body["error"]["code"] == "invalid_audio"
    assert enqueued == []


async def test_corrupt_audio_with_a_valid_header_is_422(
    db_client: AsyncClient, channel_id: str, tmp_path: Path
) -> None:
    broken = tmp_path / "broken.webm"
    broken.write_bytes(b"\x1a\x45\xdf\xa3" + b"\x00" * 200)

    status, _ = await _upload(db_client, channel_id, broken)

    assert status == 422


async def test_non_member_cannot_upload(
    db_client: AsyncClient,
    channel_id: str,
    tmp_path: Path,
    make_client: Callable[[], AsyncClient],
) -> None:
    bob = make_client()
    await signup(bob, "bob")

    status, body = await _upload(bob, channel_id, make_recording(tmp_path / "r.webm", 1))

    assert status == 403
    assert body["error"]["code"] == "not_a_member"


async def test_queue_down_marks_the_message_failed_and_answers_503(
    db_client: AsyncClient, db_app: FastAPI, channel_id: str, tmp_path: Path
) -> None:
    async def broken_queue(_: uuid.UUID) -> None:
        raise ConnectionError("broker down")

    db_app.state.enqueue = broken_queue

    status, _ = await _upload(db_client, channel_id, make_recording(tmp_path / "r.webm", 1))

    assert status == 503
    pending = (await db_client.get(f"/api/channels/{channel_id}/messages")).json()["pending"]
    assert [(m["status"], m["failure_reason"]) for m in pending] == [
        ("failed", "queue_unavailable")
    ]


async def test_pending_messages_are_visible_only_to_their_sender(
    db_client: AsyncClient,
    channel_id: str,
    tmp_path: Path,
    make_client: Callable[[], AsyncClient],
) -> None:
    await _upload(db_client, channel_id, make_recording(tmp_path / "r.webm", 1))
    bob = make_client()
    await signup(bob, "bob")
    await bob.post(f"/api/channels/{channel_id}/join")

    mine = (await db_client.get(f"/api/channels/{channel_id}/messages")).json()
    theirs = (await bob.get(f"/api/channels/{channel_id}/messages")).json()

    assert len(mine["pending"]) == 1
    assert theirs == {"messages": [], "pending": [], "has_more": False}
