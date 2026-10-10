import asyncio
import json
import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.datastructures import State

from pushtalk.auth.deps import authenticate_websocket
from pushtalk.channels.errors import ChannelNotFound, NotAMember
from pushtalk.channels.presence import PresenceService
from pushtalk.channels.service import ChannelService
from pushtalk.messages.receipts import ReceiptService
from pushtalk.messages.repository import MessageRepository
from pushtalk.realtime.bus import EventBus, channel_topic, event, user_topic
from pushtalk.realtime.manager import CLOSE_UNAUTHORIZED, Connection, ConnectionManager
from pushtalk.realtime.players import PlayerRegistry

log = structlog.get_logger(__name__)
router = APIRouter()

# Not a member (or no such channel): the client stops reconnecting.
CLOSE_FORBIDDEN = 4403
# Clients ping every 25 s; a connection silent for longer than this is treated as gone.
IDLE_TIMEOUT_S = 60
# Catch-up sends at most this many messages; the client pages the rest over HTTP.
CATCHUP_LIMIT = 200


@router.websocket("/ws/channels/{channel_id}")
async def channel_socket(
    websocket: WebSocket,
    channel_id: uuid.UUID,
    since_seq: Annotated[int | None, Query(ge=0)] = None,
) -> None:
    state = websocket.app.state
    current = await authenticate_websocket(websocket)
    # Accept before closing: a refused handshake hides the close code from the browser.
    await websocket.accept()
    if current is None:
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return
    async with state.sessionmaker() as session:
        try:
            await ChannelService(session, state.presence).require_member(
                current.user.id, channel_id
            )
        except (ChannelNotFound, NotAMember):
            await websocket.close(code=CLOSE_FORBIDDEN)
            return

    manager: ConnectionManager = state.connections
    presence: PresenceService = state.presence
    players = PlayerRegistry(state.redis)
    bus = EventBus(state.redis)
    user_id = current.user.id
    connection = Connection(websocket, user_id, current.claims.session_id)
    topic = channel_topic(channel_id)
    # Subscribed before reading history, so a message published meanwhile is not lost
    # (it may arrive twice; clients ignore a seq they already have).
    await manager.register(connection, [topic, user_topic(user_id)])
    log.info("ws.connected", channel_id=str(channel_id), user_id=str(user_id))
    try:
        await connection.send(event("hello", connection_id=str(connection.id)))
        if await presence.connect(channel_id, user_id, connection.id):
            await bus.publish(topic, event("presence.update", user_id=str(user_id), online=True))
        online = await presence.online(channel_id)
        await connection.send(event("presence.snapshot", online_user_ids=sorted(map(str, online))))
        if since_seq is not None:
            async with state.sessionmaker() as session:
                missed, has_more = await MessageRepository(session).list_ready(
                    channel_id, after_seq=since_seq, before_seq=None, limit=CATCHUP_LIMIT
                )
            await connection.send(
                event(
                    "catchup",
                    messages=[message.model_dump(mode="json") for message in missed],
                    has_more=has_more,
                )
            )
        await players.claim_if_free(channel_id, user_id, connection.id)

        while True:
            async with asyncio.timeout(IDLE_TIMEOUT_S):
                raw = await websocket.receive_text()
            message = _parse(raw)
            match message.get("type"):
                case "ping":
                    await presence.heartbeat(channel_id, user_id, connection.id)
                    await connection.send(event("pong"))
                case "receipt":
                    await _record_receipt(state, bus, user_id, channel_id, message.get("data"))
                case "playback.claim":
                    await players.claim(channel_id, user_id, connection.id)
                case _:
                    await connection.send(
                        event("error", code="unknown_event", message="Unknown event type.")
                    )
    except TimeoutError:
        await websocket.close()
    except (WebSocketDisconnect, RuntimeError):
        # The client left, or the server closed the socket (e.g. the session was logged out).
        pass
    finally:
        await manager.unregister(connection)
        await players.release(channel_id, user_id, connection.id)
        if await presence.disconnect(channel_id, user_id, connection.id):
            await bus.publish(topic, event("presence.update", user_id=str(user_id), online=False))
        log.info("ws.disconnected", channel_id=str(channel_id), user_id=str(user_id))


async def _record_receipt(
    state: State, bus: EventBus, user_id: uuid.UUID, channel_id: uuid.UUID, data: object
) -> None:
    if not isinstance(data, dict) or data.get("status") not in ("delivered", "played"):
        return
    try:
        message_id = uuid.UUID(str(data.get("message_id")))
    except ValueError:
        return
    async with state.sessionmaker() as session:
        await ReceiptService(session, bus).record(user_id, channel_id, message_id, data["status"])


def _parse(raw: str) -> dict[str, object]:
    """A client event, or an empty dict for anything that is not a JSON object."""
    try:
        message = json.loads(raw)
    except ValueError:
        return {}
    return message if isinstance(message, dict) else {}
