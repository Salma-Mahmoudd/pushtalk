import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from pushtalk.core.security import ACCESS_COOKIE
from pushtalk.messages.models import MessageReceipt
from pushtalk.messages.processing import ProcessingContext, process_message
from pushtalk.messages.receipts import ReceiptService
from pushtalk.realtime.bus import EventBus
from pushtalk.realtime.players import PlayerRegistry
from tests.helpers import create_channel, signup
from tests.recordings import make_recording, requires_ffmpeg
from tests.ws import WsClient

pytestmark = [pytest.mark.integration, requires_ffmpeg]


def _cookies(client: AsyncClient) -> dict[str, str]:
    return {ACCESS_COOKIE: client.cookies[ACCESS_COOKIE]}


@pytest.fixture
async def room(
    db_app: FastAPI, db_client: AsyncClient, make_client: Callable[[], AsyncClient], tmp_path: Any
) -> dict[str, Any]:
    """alice (db_client) and bob in one channel, with two ready messages from alice."""
    alice = await signup(db_client, "alice")
    channel = await create_channel(db_client, "general")
    bob_client = make_client()
    bob = await signup(bob_client, "bob")
    await bob_client.post(f"/api/channels/{channel['id']}/join")
    ctx = ProcessingContext(
        sessionmaker=db_app.state.sessionmaker,
        storage=db_app.state.storage,
        bus=EventBus(db_app.state.redis),
    )
    ids = []
    for n in range(2):
        path = make_recording(tmp_path / f"{n}.webm", 1)
        response = await db_client.post(
            f"/api/channels/{channel['id']}/messages",
            files={"file": (path.name, path.read_bytes(), "audio/webm")},
            data={"client_msg_id": str(uuid.uuid4())},
        )
        ids.append(response.json()["id"])
        await process_message(uuid.UUID(ids[-1]), ctx)
    return {"alice": alice, "bob": bob, "bob_client": bob_client, "channel": channel, "ids": ids}


async def test_catchup_sends_messages_after_since_seq(
    db_app: FastAPI, room: dict[str, Any]
) -> None:
    path = f"/ws/channels/{room['channel']['id']}"
    async with WsClient(db_app, path, _cookies(room["bob_client"]), query="since_seq=1") as ws:
        await ws.accepted()
        catchup = await ws.next_event("catchup")

    assert [m["seq"] for m in catchup["data"]["messages"]] == [2]
    assert catchup["data"]["has_more"] is False


async def test_no_catchup_without_since_seq(db_app: FastAPI, room: dict[str, Any]) -> None:
    path = f"/ws/channels/{room['channel']['id']}"
    async with WsClient(db_app, path, _cookies(room["bob_client"])) as ws:
        await ws.accepted()
        await ws.send_json({"type": "ping"})
        before_pong = await ws.events_until("pong")

    assert before_pong[0] == "hello"
    assert "catchup" not in before_pong


async def test_receipts_reach_the_sender_and_ignore_repeats(
    db_app: FastAPI, db_client: AsyncClient, room: dict[str, Any]
) -> None:
    channel_id, first = room["channel"]["id"], room["ids"][0]
    path = f"/ws/channels/{channel_id}"
    # Sockets open one after the other: the tests share one database connection.
    async with WsClient(db_app, path, _cookies(db_client)) as alice_ws:
        await alice_ws.accepted()
        await alice_ws.next_event("presence.snapshot")
        async with WsClient(db_app, path, _cookies(room["bob_client"])) as bob_ws:
            await bob_ws.accepted()
            await bob_ws.next_event("presence.snapshot")

            delivered_report = {"message_id": first, "status": "delivered"}
            played_report = {"message_id": first, "status": "played"}
            await bob_ws.send_json({"type": "receipt", "data": delivered_report})
            delivered = await alice_ws.next_event("receipt.updated")
            await bob_ws.send_json({"type": "receipt", "data": delivered_report})  # ignored
            await bob_ws.send_json({"type": "receipt", "data": played_report})
            played = await alice_ws.next_event("receipt.updated")

    assert delivered["data"] | {"recipient": None} == {
        "message_id": first,
        "channel_id": channel_id,
        "delivered": 1,
        "played": 0,
        "total": 1,
        "recipient": None,
    }
    assert delivered["data"]["recipient"]["username"] == "bob"
    # The repeated "delivered" produced no event: the next one is the "played" update.
    assert (played["data"]["delivered"], played["data"]["played"]) == (1, 1)
    assert played["data"]["recipient"]["played_at"] is not None

    details = (await db_client.get(f"/api/messages/{first}/receipts")).json()
    assert [(r["username"], r["played_at"] is not None) for r in details] == [("bob", True)]

    history = (await db_client.get(f"/api/channels/{channel_id}/messages")).json()["messages"]
    assert [m["receipts"] for m in history] == [
        {"delivered": 1, "played": 1, "total": 1},
        {"delivered": 0, "played": 0, "total": 1},
    ]


async def test_own_messages_get_no_receipts(
    db_app: FastAPI, db_client: AsyncClient, room: dict[str, Any]
) -> None:
    channel_id, first = room["channel"]["id"], room["ids"][0]
    async with WsClient(db_app, f"/ws/channels/{channel_id}", _cookies(db_client)) as ws:
        await ws.accepted()
        await ws.send_json({"type": "receipt", "data": {"message_id": first, "status": "played"}})
        await ws.send_json({"type": "ping"})
        await ws.next_event("pong")

    details = (await db_client.get(f"/api/messages/{first}/receipts")).json()
    assert details == [
        {"user_id": room["bob"]["id"], "username": "bob", "delivered_at": None, "played_at": None}
    ]


async def test_receipt_details_are_for_the_sender_only(room: dict[str, Any]) -> None:
    response = await room["bob_client"].get(f"/api/messages/{room['ids'][0]}/receipts")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_the_sender"


async def test_last_focused_tab_becomes_the_player(
    db_app: FastAPI, db_client: AsyncClient, room: dict[str, Any]
) -> None:
    path = f"/ws/channels/{room['channel']['id']}"
    async with WsClient(db_app, path, _cookies(db_client)) as tab_1:
        await tab_1.accepted()
        first_id = (await tab_1.next_event("hello"))["data"]["connection_id"]
        claimed = await tab_1.next_event("playback.claimed")
        assert claimed["data"]["connection_id"] == first_id  # the first tab plays

        async with WsClient(db_app, path, _cookies(db_client)) as tab_2:
            await tab_2.accepted()
            second_id = (await tab_2.next_event("hello"))["data"]["connection_id"]
            await tab_2.send_json({"type": "playback.claim"})  # tab 2 is focused
            moved = await tab_1.next_event(
                "playback.claimed", lambda data: data["connection_id"] == second_id
            )
            assert moved["data"]["channel_id"] == room["channel"]["id"]

        # Tab 2 closed while playing: tab 1 hears that nobody plays now.
        released = await tab_1.next_event(
            "playback.claimed", lambda data: data["connection_id"] is None
        )
        assert released["data"]["connection_id"] is None


async def test_a_tab_joining_while_another_plays_learns_it_must_stay_silent(
    db_app: FastAPI, db_client: AsyncClient, room: dict[str, Any]
) -> None:
    path = f"/ws/channels/{room['channel']['id']}"
    async with WsClient(db_app, path, _cookies(db_client)) as tab_1:
        await tab_1.accepted()
        first_id = (await tab_1.next_event("hello"))["data"]["connection_id"]
        async with WsClient(db_app, path, _cookies(db_client)) as tab_2:
            await tab_2.accepted()
            second_id = (await tab_2.next_event("hello"))["data"]["connection_id"]
            told = await tab_2.next_event("playback.claimed")

            assert told["data"]["connection_id"] == first_id != second_id


async def test_claim_if_free_takes_over_only_when_nobody_plays(
    db_app: FastAPI, db_client: AsyncClient, room: dict[str, Any]
) -> None:
    path = f"/ws/channels/{room['channel']['id']}"
    async with WsClient(db_app, path, _cookies(db_client)) as tab_1:
        await tab_1.accepted()
        first_id = (await tab_1.next_event("hello"))["data"]["connection_id"]
        async with WsClient(db_app, path, _cookies(db_client)) as tab_2:
            await tab_2.accepted()
            second_id = (await tab_2.next_event("hello"))["data"]["connection_id"]
            await tab_2.send_json({"type": "playback.claim_if_free"})  # tab 1 still plays
            await tab_2.send_json({"type": "ping"})
            await tab_2.next_event("pong")
            assert (
                await PlayerRegistry(db_app.state.redis).active(
                    uuid.UUID(room["channel"]["id"]), uuid.UUID(room["alice"]["id"])
                )
                == first_id
            )

        # Tab 2 played nothing and left; now tab 1 leaves and a new tab asks.
    async with WsClient(db_app, path, _cookies(db_client)) as tab_3:
        await tab_3.accepted()
        third_id = (await tab_3.next_event("hello"))["data"]["connection_id"]
        told = await tab_3.next_event("playback.claimed")

        assert told["data"]["connection_id"] == third_id  # free again: the new tab plays
    assert second_id not in (first_id, third_id)


async def test_one_receipt_event_can_cover_many_messages(
    db_app: FastAPI, db_client: AsyncClient, room: dict[str, Any]
) -> None:
    channel_id = room["channel"]["id"]
    report = {"message_ids": [*room["ids"], "not-a-uuid"], "status": "delivered"}
    async with WsClient(db_app, f"/ws/channels/{channel_id}", _cookies(room["bob_client"])) as ws:
        await ws.accepted()
        await ws.send_json({"type": "receipt", "data": report})
        await ws.send_json({"type": "ping"})
        await ws.next_event("pong")

    history = (await db_client.get(f"/api/channels/{channel_id}/messages")).json()["messages"]
    assert [m["receipts"]["delivered"] for m in history] == [1, 1]


async def test_a_receipt_another_tab_already_stored_is_ignored_without_error(
    db_app: FastAPI, db_client: AsyncClient, room: dict[str, Any]
) -> None:
    """Two tabs report the same message at once: the second insert must not fail."""
    first = uuid.UUID(room["ids"][0])
    bob_id = uuid.UUID(room["bob"]["id"])
    channel_id = uuid.UUID(room["channel"]["id"])
    async with db_app.state.sessionmaker() as session:
        # The other tab's row, written by a plain insert as if it won the race.
        session.add(MessageReceipt(message_id=first, user_id=bob_id))
        await session.commit()
    bus = EventBus(db_app.state.redis)
    async with db_app.state.sessionmaker() as session:
        await ReceiptService(session, bus).record(bob_id, channel_id, first, "delivered")
    async with db_app.state.sessionmaker() as session:
        await ReceiptService(session, bus).record(bob_id, channel_id, first, "played")
        await ReceiptService(session, bus).record(bob_id, channel_id, first, "played")

    details = (await db_client.get(f"/api/messages/{first}/receipts")).json()
    assert details[0]["played_at"] is not None


async def test_a_failing_event_does_not_close_the_connection(
    db_app: FastAPI, room: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failing(*_: object) -> None:
        raise ValueError("database hiccup")

    monkeypatch.setattr(ReceiptService, "record", failing)
    path = f"/ws/channels/{room['channel']['id']}"
    async with WsClient(db_app, path, _cookies(room["bob_client"])) as ws:
        await ws.accepted()
        report = {"message_id": room["ids"][0], "status": "delivered"}
        await ws.send_json({"type": "receipt", "data": report})
        error = await ws.next_event("error")
        await ws.send_json({"type": "ping"})
        await ws.next_event("pong")  # still connected

    assert error["data"]["code"] == "event_failed"
