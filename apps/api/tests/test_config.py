import pytest
from pydantic import ValidationError

from pushtalk.core.config import Settings


def test_defaults_work_without_environment() -> None:
    settings = Settings()

    assert settings.log_level == "INFO"
    assert settings.log_format == "json"
    assert "http://localhost:8080" in settings.allowed_origins


def test_allowed_origins_from_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://a.example, https://b.example/")

    assert Settings().allowed_origins == ["https://a.example", "https://b.example"]


def test_invalid_log_level_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "LOUD")

    with pytest.raises(ValidationError):
        Settings()
