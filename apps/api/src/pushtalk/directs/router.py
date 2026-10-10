from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from pushtalk.auth.deps import CurrentUserDep
from pushtalk.channels.schemas import UserOut
from pushtalk.core.deps import RateLimiterDep, SessionDep, SettingsDep
from pushtalk.directs.schemas import DirectOpen, DirectOut
from pushtalk.directs.service import DirectService
from pushtalk.infra.rate_limit import RateLimitRule
from pushtalk.realtime.bus import EventBus

router = APIRouter(tags=["direct messages"])


def get_direct_service(request: Request, session: SessionDep) -> DirectService:
    state = request.app.state
    return DirectService(session, state.presence, EventBus(state.redis))


DirectServiceDep = Annotated[DirectService, Depends(get_direct_service)]


@router.get("/api/users")
async def search_users(
    current: CurrentUserDep,
    service: DirectServiceDep,
    query: Annotated[str, Query(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_]+$")],
) -> list[UserOut]:
    """Usernames starting with `query` (up to 20), to start a conversation with."""
    return await service.search_users(current.user, query)


@router.get("/api/dms")
async def list_directs(current: CurrentUserDep, service: DirectServiceDep) -> list[DirectOut]:
    return await service.list_for(current.user)


@router.post("/api/dms", responses={201: {"description": "The conversation was created"}})
async def open_direct(
    body: DirectOpen,
    response: Response,
    current: CurrentUserDep,
    service: DirectServiceDep,
    limiter: RateLimiterDep,
    settings: SettingsDep,
) -> DirectOut:
    """The conversation with a user: 200 if it exists, 201 when created now."""
    rule = RateLimitRule.parse("dm_create", settings.rate_limit_dm_create_user)
    await limiter.hit(rule, str(current.user.id))
    direct, created = await service.open(current.user, body.user_id)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return direct
