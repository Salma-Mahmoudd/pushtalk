import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from pushtalk.auth.deps import CurrentUserDep
from pushtalk.channels.presence import PresenceService
from pushtalk.channels.schemas import ChannelCreate, ChannelOut, MemberOut
from pushtalk.channels.service import ChannelService
from pushtalk.core.deps import RateLimiterDep, SessionDep, SettingsDep
from pushtalk.infra.rate_limit import RateLimitRule
from pushtalk.realtime.bus import EventBus

router = APIRouter(prefix="/api/channels", tags=["channels"])


def get_channel_service(request: Request, session: SessionDep) -> ChannelService:
    presence: PresenceService = request.app.state.presence
    return ChannelService(session, presence, EventBus(request.app.state.redis))


ChannelServiceDep = Annotated[ChannelService, Depends(get_channel_service)]


@router.get("")
async def list_channels(current: CurrentUserDep, service: ChannelServiceDep) -> list[ChannelOut]:
    return await service.list_all(current.user)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_channel(
    body: ChannelCreate,
    current: CurrentUserDep,
    service: ChannelServiceDep,
    limiter: RateLimiterDep,
    settings: SettingsDep,
) -> ChannelOut:
    rule = RateLimitRule.parse("channel_create", settings.rate_limit_channel_create_user)
    await limiter.hit(rule, str(current.user.id))
    return await service.create(current.user, body.name)


@router.get("/{channel_id}")
async def get_channel(
    channel_id: uuid.UUID, current: CurrentUserDep, service: ChannelServiceDep
) -> ChannelOut:
    return await service.get(current.user, channel_id)


@router.post("/{channel_id}/join", status_code=status.HTTP_204_NO_CONTENT)
async def join_channel(
    channel_id: uuid.UUID, current: CurrentUserDep, service: ChannelServiceDep
) -> Response:
    await service.join(current.user, channel_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{channel_id}/members")
async def list_members(
    channel_id: uuid.UUID, current: CurrentUserDep, service: ChannelServiceDep
) -> list[MemberOut]:
    return await service.members(current.user, channel_id)
