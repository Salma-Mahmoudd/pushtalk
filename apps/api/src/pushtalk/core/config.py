from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEV_JWT_SECRET = "dev-insecure-change-me-local-development-only"
RateLimitSetting = Annotated[str, Field(pattern=r"^[1-9][0-9]*/[1-9][0-9]*$")]


class Settings(BaseSettings):
    """Every value comes from an environment variable; defaults suit local development."""

    model_config = SettingsConfigDict(frozen=True, extra="ignore")

    # Defaults match docker-compose.dev.yml, for running the API outside Docker.
    database_url: PostgresDsn = PostgresDsn(
        "postgresql+asyncpg://pushtalk:pushtalk@localhost:5433/pushtalk"
    )
    redis_url: RedisDsn = RedisDsn("redis://localhost:6380/0")

    # Auth. The default secret only suits local development; deployments set JWT_SECRET.
    jwt_secret: SecretStr = SecretStr(DEV_JWT_SECRET)
    access_token_ttl_min: int = 15
    refresh_token_ttl_days: int = 7
    # A rotated refresh token presented again within this window is a retry, not theft.
    refresh_reuse_grace_s: int = 10
    # Browsers accept Secure cookies on http://localhost; other plain-HTTP hosts need false.
    cookie_secure: bool = True

    # Rate limits as "<requests>/<seconds>".
    rate_limit_login_username: RateLimitSetting = "10/900"
    rate_limit_login_ip: RateLimitSetting = "30/900"
    rate_limit_signup_ip: RateLimitSetting = "5/3600"
    rate_limit_upload_user: RateLimitSetting = "20/60"
    rate_limit_upload_user_daily: RateLimitSetting = "200/86400"
    rate_limit_channel_create_user: RateLimitSetting = "10/3600"
    # Events a client may send per WebSocket connection; the excess is dropped with an error.
    rate_limit_ws_events: RateLimitSetting = "30/1"

    # Voice messages. Media is stored on disk (a Docker volume shared by api and worker).
    media_dir: Path = Path("var/media")
    max_upload_bytes: int = 10 * 1024 * 1024
    min_duration_ms: int = 500
    max_duration_ms: int = 60_000
    # Celery broker (Redis database 1, apart from pub/sub and presence in database 0).
    celery_broker_url: RedisDsn = RedisDsn("redis://localhost:6380/1")

    # Transcription: a second worker step after a message is ready; "off" skips it.
    transcribe_provider: Literal["local", "openai", "off"] = "local"
    # faster-whisper model (tiny, base, small, medium, large-v3, ...); the image ships "base",
    # other models are downloaded into whisper_model_dir on first use.
    whisper_model: str = "base"
    whisper_model_dir: Path = Path("var/whisper-models")
    # A language code such as "en" or "ar"; empty detects the language of each message.
    transcribe_language: str = ""
    # Only for transcribe_provider="openai".
    openai_api_key: SecretStr | None = None
    openai_transcribe_model: str = "gpt-4o-mini-transcribe"

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"
    # Origins allowed to send state-changing requests and open WebSockets (CSRF protection).
    allowed_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:8080",
        "http://localhost:5173",
    ]

    @field_validator("jwt_secret")
    @classmethod
    def secret_long_enough(cls, value: SecretStr) -> SecretStr:
        """HS256 needs a key of at least 32 bytes (RFC 7518, section 3.2)."""
        if len(value.get_secret_value().encode()) < 32:
            raise ValueError("JWT_SECRET must be at least 32 bytes long")
        return value

    @field_validator("openai_api_key", mode="before")
    @classmethod
    def blank_key_is_none(cls, value: object) -> object:
        """Compose passes an unset OPENAI_API_KEY as an empty string."""
        secret = value.get_secret_value() if isinstance(value, SecretStr) else value
        return None if secret == "" else value

    @model_validator(mode="after")
    def openai_needs_a_key(self) -> "Settings":
        if self.transcribe_provider == "openai" and self.openai_api_key is None:
            raise ValueError("TRANSCRIBE_PROVIDER=openai needs OPENAI_API_KEY")
        return self

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        """Accept a comma-separated string: ALLOWED_ORIGINS=https://a.example,https://b.example."""
        if isinstance(value, str):
            return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
