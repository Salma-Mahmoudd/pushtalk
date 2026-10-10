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
from pushtalk.core.config import Settings
from pushtalk.directs.service import APP_PRESENCE
from pushtalk.infra.rate_limit import LocalRateLimiter, RateLimitRule
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
# One receipt event may cover this many messages (e.g. everything a catch-up delivered).
RECEIPT_BATCH_LIMIT = CATCHUP_LIMIT


@router.websocket("/ws/channels/{channel_id}")
async def channel_socket(
    websocket: WebSocket,
    channel_id: uuid.UUID,
    since_seq: Annotated[int | None, Query(ge=0)] = None,
) -> None:
    state = websocket.app.state
    settings: Settings = state.settings
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
    events_limit = LocalRateLimiter(RateLimitRule.parse("ws_events", settings.rate_limit_ws_events))
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
        # Tell this connection who plays, even when it is another one: otherwise a tab that
        # joins while another tab plays would never learn that it must stay silent.
        player = await players.active(channel_id, user_id)
        await connection.send(
            event("playback.claimed", channel_id=str(channel_id), connection_id=player)
        )

        while True:
            async with asyncio.timeout(IDLE_TIMEOUT_S):
                raw = await websocket.receive_text()
            message = _parse(raw)
            if not events_limit.allow():
                await connection.send(
                    event(
                        "error",
                        code="rate_limited",
                        message="Too many events; this one was dropped.",
                    )
                )
                continue
            try:
                match message.get("type"):
                    case "ping":
                        await presence.heartbeat(channel_id, user_id, connection.id)
                        await connection.send(event("pong"))
                    case "receipt":
                        await _record_receipt(state, bus, user_id, channel_id, message.get("data"))
                    case "playback.claim":
                        await players.claim(channel_id, user_id, connection.id)
                    case "playback.claim_if_free":
                        # Nobody plays and no tab of the user has focus: the first to ask wins.
                        await players.claim_if_free(channel_id, user_id, connection.id)
                    case _:
                        await connection.send(
                            event("error", code="unknown_event", message="Unknown event type.")
                        )
            except (WebSocketDisconnect, RuntimeError):
                raise
            except Exception:
                # One failing event must not end the connection (and with it playback).
                log.exception("ws.event_failed", event_type=str(message.get("type")))
                await connection.send(
                    event("error", code="event_failed", message="This event could not be handled.")
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
    """Accepts {message_id, status} or {message_ids: [...], status}; invalid ids are skipped."""
    if not isinstance(data, dict) or data.get("status") not in ("delivered", "played"):
        return
    raw_ids = data.get("message_ids", [data.get("message_id")])
    if not isinstance(raw_ids, list):
        return
    message_ids: list[uuid.UUID] = []
    for raw_id in raw_ids[:RECEIPT_BATCH_LIMIT]:
        try:
            message_ids.append(uuid.UUID(str(raw_id)))
        except ValueError:
            continue
    async with state.sessionmaker() as session:
        receipts = ReceiptService(session, bus)
        for message_id in message_ids:
            await receipts.record(user_id, channel_id, message_id, data["status"])


def _parse(raw: str) -> dict[str, object]:
    """A client event, or an empty dict for anything that is not a JSON object."""
    try:
        message = json.loads(raw)
    except ValueError:
        return {}
    return message if isinstance(message, dict) else {}


@router.websocket("/ws/me")
async def user_socket(websocket: WebSocket) -> None:
    """The user's app-wide socket: events for the user (new conversations) and "online
    anywhere" presence, shown next to direct conversations."""
    state = websocket.app.state
    settings: Settings = state.settings
    current = await authenticate_websocket(websocket)
    await websocket.accept()
    if current is None:
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return

    manager: ConnectionManager = state.connections
    presence: PresenceService = state.presence
    user_id = current.user.id
    connection = Connection(websocket, user_id, current.claims.session_id)
    events_limit = LocalRateLimiter(RateLimitRule.parse("ws_events", settings.rate_limit_ws_events))
    await manager.register(connection, [user_topic(user_id)])
    try:
        await connection.send(event("hello", connection_id=str(connection.id)))
        await presence.connect(APP_PRESENCE, user_id, connection.id)
        while True:
            async with asyncio.timeout(IDLE_TIMEOUT_S):
                raw = await websocket.receive_text()
            message = _parse(raw)
            if not events_limit.allow():
                await connection.send(
                    event(
                        "error",
                        code="rate_limited",
                        message="Too many events; this one was dropped.",
                    )
                )
                continue
            if message.get("type") == "ping":
                await presence.heartbeat(APP_PRESENCE, user_id, connection.id)
                await connection.send(event("pong"))
            else:
                await connection.send(
                    event("error", code="unknown_event", message="Unknown event type.")
                )
    except TimeoutError:
        await websocket.close()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await manager.unregister(connection)
        await presence.disconnect(APP_PRESENCE, user_id, connection.id)
