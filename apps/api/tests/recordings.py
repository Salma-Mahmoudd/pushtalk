"""Test recordings generated with ffmpeg (a 440 Hz tone), in the formats browsers upload."""

import shutil
import subprocess
from pathlib import Path

import pytest

requires_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg is not installed"
)


def make_recording(path: Path, seconds: float, *, streamed: bool = False) -> Path:
    """Opus in WebM. `streamed` writes it the way MediaRecorder does: without a duration header."""
    command = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:duration={seconds}",
        "-ac",
        "1",
        "-c:a",
        "libopus",
        "-b:a",
        "16k",
        "-f",
        "webm",
    ]
    if streamed:
        path.write_bytes(subprocess.run([*command, "-"], check=True, capture_output=True).stdout)
    else:
        subprocess.run([*command, str(path)], check=True)
    return path
