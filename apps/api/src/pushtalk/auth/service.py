import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pushtalk.auth.errors import InvalidCredentials, RefreshInvalid, UsernameTaken
from pushtalk.auth.models import RefreshToken, User
from pushtalk.auth.repository import RefreshTokenRepository, UserRepository
from pushtalk.auth.schemas import LoginIn, SignupIn
from pushtalk.core.config import Settings
from pushtalk.core.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)
from pushtalk.realtime.bus import EventBus, event, user_topic

log = structlog.get_logger(__name__)


def revoked_session_key(session_id: uuid.UUID) -> str:
    """Redis key marking a logged-out session; it outlives every access token of the session."""
    return f"session:revoked:{session_id}"


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class ClientInfo:
    user_agent: str | None
    ip: str | None


@dataclass(frozen=True)
class IssuedSession:
    user: User
    session_id: uuid.UUID
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        redis: Redis,
        settings: Settings,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._session = session
        self._redis = redis
        self._settings = settings
        self._clock = clock
        self._users = UserRepository(session)
        self._tokens = RefreshTokenRepository(session)

    async def signup(self, data: SignupIn, client: ClientInfo) -> IssuedSession:
        username = data.username.lower()
        if await self._users.get_by_username(username) is not None:
            raise UsernameTaken()
        # argon2 is deliberately slow; a thread keeps other requests running meanwhile.
        user = User(
            username=username, password_hash=await asyncio.to_thread(hash_password, data.password)
        )
        try:
            await self._users.add(user)
        except IntegrityError:  # Another signup took the name between the check and the insert.
            await self._session.rollback()
            raise UsernameTaken() from None
        issued, _ = await self._issue(user, uuid.uuid4(), client)
        await self._session.commit()
        log.info("auth.signup", user_id=str(user.id))
        return issued

    async def login(self, data: LoginIn, client: ClientInfo) -> IssuedSession:
        user = await self._users.get_by_username(data.username.lower())
        # Verifies a dummy hash for unknown usernames, so both failures take the same time.
        valid = await asyncio.to_thread(
            verify_password, data.password, user.password_hash if user else None
        )
        if user is None or not valid:
            raise InvalidCredentials()
        issued, _ = await self._issue(user, uuid.uuid4(), client)
        await self._session.commit()
        log.info("auth.login", user_id=str(user.id), session_id=str(issued.session_id))
        return issued

    async def refresh(self, raw_token: str, client: ClientInfo) -> IssuedSession:
        now = self._clock()
        token = await self._tokens.get_by_hash_for_update(hash_refresh_token(raw_token))
        if token is None or token.revoked_at is not None or token.expires_at <= now:
            raise RefreshInvalid()

        if token.rotated_at is not None:
            grace = timedelta(seconds=self._settings.refresh_reuse_grace_s)
            if now - token.rotated_at > grace:
                # An old token came back: someone else may hold this session. End all of it.
                await self._revoke_session(token, now)
                await self._session.commit()
                log.warning(
                    "auth.refresh_reuse_detected",
                    user_id=str(token.user_id),
                    session_id=str(token.family_id),
                )
                raise RefreshInvalid()

        user = await self._users.get(token.user_id)
        if user is None:
            raise RefreshInvalid()
        issued, replacement = await self._issue(user, token.family_id, client)
        # Within the grace window this supersedes the earlier replacement (lost-response retry).
        if token.replaced_by_id is not None:
            await self._tokens.revoke(token.replaced_by_id, now)
        token.rotated_at = token.rotated_at or now
        token.replaced_by_id = replacement.id
        await self._session.commit()
        return issued

    async def logout(self, raw_token: str | None) -> None:
        if raw_token is None:
            return
        token = await self._tokens.get_by_hash_for_update(hash_refresh_token(raw_token))
        if token is not None:
            await self._revoke_session(token, self._clock())
            await self._session.commit()
            log.info("auth.logout", user_id=str(token.user_id), session_id=str(token.family_id))

    async def _issue(
        self, user: User, session_id: uuid.UUID, client: ClientInfo
    ) -> tuple[IssuedSession, RefreshToken]:
        now = self._clock()
        access_token, access_expires_at = create_access_token(
            user.id,
            session_id,
            secret=self._settings.jwt_secret.get_secret_value(),
            ttl=timedelta(minutes=self._settings.access_token_ttl_min),
            now=now,
        )
        raw_refresh = new_refresh_token()
        refresh = RefreshToken(
            id=uuid.uuid4(),
            user_id=user.id,
            family_id=session_id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=now + timedelta(days=self._settings.refresh_token_ttl_days),
            user_agent=client.user_agent,
            ip=client.ip,
        )
        await self._tokens.add(refresh)
        issued = IssuedSession(
            user=user,
            session_id=session_id,
            access_token=access_token,
            access_expires_at=access_expires_at,
            refresh_token=raw_refresh,
            refresh_expires_at=refresh.expires_at,
        )
        return issued, refresh

    async def _revoke_session(self, token: RefreshToken, now: datetime) -> None:
        await self._tokens.revoke_family(token.family_id, now)
        # Access tokens are not stored; this marker rejects them until they expire anyway.
        await self._redis.set(
            revoked_session_key(token.family_id),
            "1",
            ex=self._settings.access_token_ttl_min * 60,
        )
        # Open WebSockets of this session close on every API process.
        await EventBus(self._redis).publish(
            user_topic(token.user_id), event("session.revoked", session_id=str(token.family_id))
        )
