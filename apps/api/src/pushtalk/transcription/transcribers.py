"""Speech-to-text providers. Each call blocks, so jobs run them in a thread."""

import functools
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pushtalk.core.config import Settings

OPENAI_API_URL = "https://api.openai.com/v1"


@dataclass(frozen=True)
class Transcript:
    text: str
    # ISO 639-1 code (e.g. "en"); None when the provider does not report it.
    language: str | None


class Transcriber(Protocol):
    def transcribe(self, audio: Path) -> Transcript: ...


@functools.cache
def _whisper_model(name: str, model_dir: str) -> Any:
    """Loaded once per worker process: loading takes seconds, transcribing a short clip less."""
    from faster_whisper import WhisperModel  # Installed in the transcriber image only.

    return WhisperModel(name, device="cpu", compute_type="int8", download_root=model_dir)


class LocalWhisperTranscriber:
    """faster-whisper on the CPU (int8). The audio never leaves the server."""

    def __init__(self, model: str, model_dir: Path, language: str | None) -> None:
        self._model = model
        self._model_dir = model_dir
        self._language = language

    def transcribe(self, audio: Path) -> Transcript:
        model = _whisper_model(self._model, str(self._model_dir))
        # The voice activity filter drops silence, where Whisper tends to invent words.
        segments, info = model.transcribe(str(audio), language=self._language, vad_filter=True)
        text = " ".join(segment.text.strip() for segment in segments)
        return Transcript(text=text.strip(), language=info.language)


class OpenAITranscriber:
    """OpenAI's transcription endpoint; the audio is sent to OpenAI."""

    def __init__(
        self, api_key: str, model: str, language: str | None, base_url: str = OPENAI_API_URL
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._language = language
        self._base_url = base_url

    def transcribe(self, audio: Path) -> Transcript:
        import httpx  # Installed in the transcriber image only.

        form = {"model": self._model, "response_format": "json"}
        if self._language:
            form["language"] = self._language
        with audio.open("rb") as file:
            response = httpx.post(
                f"{self._base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                data=form,
                files={"file": (audio.name, file, "audio/ogg")},
                timeout=60,
            )
        response.raise_for_status()
        body = response.json()
        return Transcript(text=str(body["text"]).strip(), language=self._language)


def get_transcriber(settings: Settings) -> Transcriber | None:
    """The configured provider, or None when transcription is off."""
    language = settings.transcribe_language or None
    match settings.transcribe_provider:
        case "off":
            return None
        case "openai":
            assert settings.openai_api_key is not None  # Settings refuse openai without a key.
            return OpenAITranscriber(
                settings.openai_api_key.get_secret_value(),
                settings.openai_transcribe_model,
                language,
            )
        case "local":
            return LocalWhisperTranscriber(
                settings.whisper_model, settings.whisper_model_dir, language
            )
