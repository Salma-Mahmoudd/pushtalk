from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Every value comes from an environment variable; defaults suit local development."""

    model_config = SettingsConfigDict(frozen=True, extra="ignore")

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"
    # Origins allowed to send state-changing requests and open WebSockets (CSRF protection).
    allowed_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:8080",
        "http://localhost:5173",
    ]

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
