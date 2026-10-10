"""Audio checks and conversion with ffprobe/ffmpeg, run as subprocesses with time limits."""

import asyncio
import json
from array import array
from dataclasses import dataclass
from pathlib import Path

_TIMEOUT_S = 60


class AudioToolError(Exception):
    """ffmpeg/ffprobe rejected the file (corrupt, unsupported) or did not finish in time."""


@dataclass(frozen=True)
class Container:
    extension: str
    mime: str


# Identified from the file's first bytes; the browser's Content-Type is never trusted.
WEBM = Container(".webm", "audio/webm")
OGG = Container(".ogg", "audio/ogg")
MP4 = Container(".m4a", "audio/mp4")
WAV = Container(".wav", "audio/wav")


def sniff(header: bytes) -> Container | None:
    if header.startswith(b"\x1a\x45\xdf\xa3"):  # EBML: WebM/Matroska (Chrome, Firefox)
        return WEBM
    if header.startswith(b"OggS"):  # Ogg (Firefox)
        return OGG
    if header[4:8] == b"ftyp":  # ISO media: MP4/M4A (Safari)
        return MP4
    if header.startswith(b"RIFF") and header[8:12] == b"WAVE":
        return WAV
    return None


async def _run(*args: str, stdin_path: Path | None = None) -> bytes:
    process = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        async with asyncio.timeout(_TIMEOUT_S):
            stdout, stderr = await process.communicate()
    except TimeoutError:
        process.kill()
        await process.wait()
        raise AudioToolError(f"{args[0]} timed out") from None
    if process.returncode != 0:
        raise AudioToolError(stderr.decode(errors="replace").strip()[-500:])
    return stdout


async def duration_ms(path: Path) -> int:
    """Real duration of the first audio stream; AudioToolError if there is none."""
    probe = json.loads(
        await _run(
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        )
    )
    if not any(stream.get("codec_type") == "audio" for stream in probe.get("streams", [])):
        raise AudioToolError("no audio stream")
    duration = probe.get("format", {}).get("duration")
    if duration not in (None, "N/A"):
        return round(float(duration) * 1000)
    # Browser recordings (WebM from MediaRecorder) often omit the duration header:
    # read the packet timestamps instead.
    packets = json.loads(
        await _run(
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "packet=pts_time,duration_time",
            "-print_format",
            "json",
            str(path),
        )
    ).get("packets", [])
    ends = [
        float(packet["pts_time"]) + float(packet.get("duration_time", 0) or 0)
        for packet in packets
        if packet.get("pts_time") not in (None, "N/A")
    ]
    if not ends:
        raise AudioToolError("duration unknown")
    return round(max(ends) * 1000)


async def transcode_to_opus(source: Path, target: Path) -> None:
    """Normalises any input to mono 48 kHz Opus at 32 kb/s in an Ogg file."""
    await _run(
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "48000",
        "-c:a",
        "libopus",
        "-b:a",
        "32k",
        "-application",
        "voip",
        str(target),
    )


async def waveform_peaks(path: Path, buckets: int = 64) -> list[int]:
    """Peak level (0 to 100, relative to the loudest bucket) of `buckets` equal slices."""
    raw = await _run(
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-i",
        str(path),
        "-ac",
        "1",
        "-ar",
        "8000",
        "-f",
        "s16le",
        "-",
    )
    samples = array("h")
    samples.frombytes(raw[: len(raw) - len(raw) % 2])
    if not samples:
        return [0] * buckets
    size = max(1, len(samples) // buckets)
    peaks = [
        max((abs(sample) for sample in samples[index * size : (index + 1) * size]), default=0)
        for index in range(buckets)
    ]
    loudest = max(peaks) or 1
    return [round(peak * 100 / loudest) for peak in peaks]
