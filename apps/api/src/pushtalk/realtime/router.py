import asyncio
import json
import uuid

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from pushtalk.auth.deps import authenticate_websocket
from pushtalk.channels.errors import ChannelNotFound, NotAMember
from pushtalk.channels.presence import PresenceService
from pushtalk.channels.service import ChannelService
from pushtalk.realtime.bus import EventBus, channel_topic, event, user_topic
from pushtalk.realtime.manager import CLOSE_UNAUTHORIZED, Connection, ConnectionManager

log = structlog.get_logger(__name__)
router = APIRouter()

# Not a member (or no such channel): the client stops reconnecting.
CLOSE_FORBIDDEN = 4403
# Clients ping every 25 s; a connection silent for longer than this is treated as gone.
IDLE_TIMEOUT_S = 60


@router.websocket("/ws/channels/{channel_id}")
async def channel_socket(websocket: WebSocket, channel_id: uuid.UUID) -> None:
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
    bus = EventBus(state.redis)
    user_id = current.user.id
    connection = Connection(websocket, user_id, current.claims.session_id)
    topic = channel_topic(channel_id)
    await manager.register(connection, [topic, user_topic(user_id)])
    log.info("ws.connected", channel_id=str(channel_id), user_id=str(user_id))
    try:
        if await presence.connect(channel_id, user_id, connection.id):
            await bus.publish(topic, event("presence.update", user_id=str(user_id), online=True))
        online = await presence.online(channel_id)
        await connection.send(event("presence.snapshot", online_user_ids=sorted(map(str, online))))

        while True:
            async with asyncio.timeout(IDLE_TIMEOUT_S):
                raw = await websocket.receive_text()
            message = _parse(raw)
            if message.get("type") == "ping":
                await presence.heartbeat(channel_id, user_id, connection.id)
                await connection.send(event("pong"))
            else:
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
        if await presence.disconnect(channel_id, user_id, connection.id):
            await bus.publish(topic, event("presence.update", user_id=str(user_id), online=False))
        log.info("ws.disconnected", channel_id=str(channel_id), user_id=str(user_id))


def _parse(raw: str) -> dict[str, object]:
    """A client event, or an empty dict for anything that is not a JSON object."""
    try:
        message = json.loads(raw)
    except ValueError:
        return {}
    return message if isinstance(message, dict) else {}
