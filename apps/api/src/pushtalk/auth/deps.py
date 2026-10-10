from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request, WebSocket
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from pushtalk.auth.errors import Unauthorized
from pushtalk.auth.models import User
from pushtalk.auth.repository import UserRepository
from pushtalk.auth.service import AuthService, revoked_session_key
from pushtalk.core.config import Settings
from pushtalk.core.deps import RedisDep, SessionDep, SettingsDep
from pushtalk.core.security import (
    ACCESS_COOKIE,
    AccessClaims,
    InvalidAccessToken,
    decode_access_token,
)


@dataclass(frozen=True)
class CurrentUser:
    user: User
    claims: AccessClaims


def get_auth_service(session: SessionDep, redis: RedisDep, settings: SettingsDep) -> AuthService:
    return AuthService(session, redis, settings)


async def _resolve(
    token: str | None, session: AsyncSession, redis: Redis, settings: Settings
) -> CurrentUser | None:
    """A valid, unrevoked access token of an existing user, or None."""
    if token is None:
        return None
    try:
        claims = decode_access_token(token, secret=settings.jwt_secret.get_secret_value())
    except InvalidAccessToken:
        return None
    if await redis.exists(revoked_session_key(claims.session_id)):
        return None
    user = await UserRepository(session).get(claims.user_id)
    return None if user is None else CurrentUser(user=user, claims=claims)


async def get_current_user(
    request: Request, session: SessionDep, redis: RedisDep, settings: SettingsDep
) -> CurrentUser:
    """The standard guard for HTTP endpoints: 401 without a valid session cookie."""
    current = await _resolve(request.cookies.get(ACCESS_COOKIE), session, redis, settings)
    if current is None:
        raise Unauthorized()
    return current


async def authenticate_websocket(websocket: WebSocket) -> CurrentUser | None:
    """The same check for WebSocket handshakes, which send the cookie too."""
    state = websocket.app.state
    async with state.sessionmaker() as session:
        return await _resolve(
            websocket.cookies.get(ACCESS_COOKIE), session, state.redis, state.settings
        )


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
