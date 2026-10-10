from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from pushtalk.auth.errors import Unauthorized
from pushtalk.auth.models import User
from pushtalk.auth.repository import UserRepository
from pushtalk.auth.service import AuthService, revoked_session_key
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


async def get_current_user(
    request: Request, session: SessionDep, redis: RedisDep, settings: SettingsDep
) -> CurrentUser:
    """The standard guard: a valid, unrevoked access token cookie of an existing user."""
    token = request.cookies.get(ACCESS_COOKIE)
    if token is None:
        raise Unauthorized()
    try:
        claims = decode_access_token(token, secret=settings.jwt_secret.get_secret_value())
    except InvalidAccessToken:
        raise Unauthorized() from None
    if await redis.exists(revoked_session_key(claims.session_id)):
        raise Unauthorized()
    user = await UserRepository(session).get(claims.user_id)
    if user is None:
        raise Unauthorized()
    return CurrentUser(user=user, claims=claims)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
