from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from pushtalk.core.config import Settings
from pushtalk.infra import audio
from pushtalk.transcription.transcribers import (
    LocalWhisperTranscriber,
    OpenAITranscriber,
    get_transcriber,
)
from tests.recordings import make_recording, requires_ffmpeg


def test_local_whisper_is_the_default() -> None:
    assert isinstance(get_transcriber(Settings()), LocalWhisperTranscriber)


def test_off_means_no_transcriber() -> None:
    assert get_transcriber(Settings(transcribe_provider="off")) is None


def test_openai_without_a_key_is_refused_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        Settings(transcribe_provider="openai")
    # Compose passes an unset variable as an empty string.
    monkeypatch.setenv("OPENAI_API_KEY", "")
    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        Settings(transcribe_provider="openai")


def test_openai_sends_the_audio_with_model_and_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(
        transcribe_provider="openai",
        openai_api_key=SecretStr("sk-test"),
        transcribe_language="en",
    )
    transcriber = get_transcriber(settings)
    assert isinstance(transcriber, OpenAITranscriber)
    sent: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> httpx.Response:
        sent.update(url=url, **kwargs)
        return httpx.Response(
            200, json={"text": " Hello there. "}, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    audio = tmp_path / "clip.ogg"
    audio.write_bytes(b"OggS")

    transcript = transcriber.transcribe(audio)

    assert sent["url"] == "https://api.openai.com/v1/audio/transcriptions"
    assert sent["headers"] == {"Authorization": "Bearer sk-test"}
    assert sent["data"] == {
        "model": "gpt-4o-mini-transcribe",
        "response_format": "json",
        "language": "en",
    }
    assert (transcript.text, transcript.language) == ("Hello there.", "en")


@requires_ffmpeg
async def test_whisper_can_decode_the_processed_audio(tmp_path: Path) -> None:
    """faster-whisper reads audio through PyAV; an incompatible PyAV fails right here."""
    from faster_whisper import decode_audio

    processed = tmp_path / "processed.ogg"
    await audio.transcode_to_opus(make_recording(tmp_path / "upload.webm", 1), processed)

    samples = decode_audio(str(processed), sampling_rate=16_000)

    assert abs(len(samples) - 16_000) <= 800  # One second at 16 kHz.
