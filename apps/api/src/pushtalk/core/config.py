from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr, field_validator
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
