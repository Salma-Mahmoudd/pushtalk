import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import FileResponse

from pushtalk.auth.deps import CurrentUserDep
from pushtalk.channels.router import ChannelServiceDep
from pushtalk.core.deps import RedisDep, SessionDep, SettingsDep
from pushtalk.messages.receipts import ReceiptService
from pushtalk.messages.schemas import MessageOut, MessagePage, RecipientReceipt
from pushtalk.messages.service import MessageService
from pushtalk.realtime.bus import EventBus

router = APIRouter(tags=["messages"])


def get_message_service(
    request: Request, session: SessionDep, channels: ChannelServiceDep, settings: SettingsDep
) -> MessageService:
    state = request.app.state
    return MessageService(
        session, channels, state.storage, EventBus(state.redis), settings, state.enqueue
    )


MessageServiceDep = Annotated[MessageService, Depends(get_message_service)]


@router.post("/api/channels/{channel_id}/messages", status_code=status.HTTP_202_ACCEPTED)
async def upload_message(
    channel_id: uuid.UUID,
    current: CurrentUserDep,
    service: MessageServiceDep,
    file: Annotated[UploadFile, File(description="The recording")],
    client_msg_id: Annotated[uuid.UUID, Form(description="Client-generated id; retries reuse it")],
) -> MessageOut:
    """Validates and stores a recording, queues processing; the result arrives by WebSocket."""
    return await service.create_voice_message(current.user, channel_id, file, client_msg_id)


@router.get("/api/channels/{channel_id}/messages")
async def list_messages(
    channel_id: uuid.UUID,
    current: CurrentUserDep,
    service: MessageServiceDep,
    after_seq: Annotated[int | None, Query(ge=0)] = None,
    before_seq: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> MessagePage:
    return await service.history(
        current.user, channel_id, after_seq=after_seq, before_seq=before_seq, limit=limit
    )


@router.get("/api/messages/{message_id}/audio", response_class=FileResponse)
async def message_audio(
    message_id: uuid.UUID, current: CurrentUserDep, service: MessageServiceDep
) -> FileResponse:
    """The processed recording (Ogg/Opus), for channel members; supports Range for seeking."""
    path = await service.audio_path(current.user, message_id)
    return FileResponse(
        path, media_type="audio/ogg", headers={"Cache-Control": "private, max-age=3600"}
    )


@router.get("/api/messages/{message_id}/receipts")
async def message_receipts(
    message_id: uuid.UUID, current: CurrentUserDep, session: SessionDep, redis: RedisDep
) -> list[RecipientReceipt]:
    """Who received and played one of the caller's messages (sender only)."""
    return await ReceiptService(session, EventBus(redis)).details(current.user.id, message_id)
