from pathlib import Path

import pytest

from pushtalk.infra import audio
from tests.recordings import make_recording, requires_ffmpeg


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (b"\x1a\x45\xdf\xa3" + b"\x00" * 8, audio.WEBM),
        (b"OggS" + b"\x00" * 8, audio.OGG),
        (b"\x00\x00\x00\x20ftypM4A ", audio.MP4),
        (b"RIFF\x00\x00\x00\x00WAVE", audio.WAV),
        (b"<html><body>", None),
        (b"", None),
    ],
)
def test_sniff_reads_the_real_type(header: bytes, expected: audio.Container | None) -> None:
    assert audio.sniff(header) == expected


@requires_ffmpeg
async def test_duration_from_header(tmp_path: Path) -> None:
    recording = make_recording(tmp_path / "a.webm", 2)

    assert abs(await audio.duration_ms(recording) - 2000) <= 50


@requires_ffmpeg
async def test_duration_without_header_like_mediarecorder(tmp_path: Path) -> None:
    recording = make_recording(tmp_path / "a.webm", 2, streamed=True)

    assert abs(await audio.duration_ms(recording) - 2000) <= 50


@requires_ffmpeg
async def test_non_audio_is_rejected(tmp_path: Path) -> None:
    fake = tmp_path / "fake.webm"
    fake.write_text("not audio at all")

    with pytest.raises(audio.AudioToolError):
        await audio.duration_ms(fake)


@requires_ffmpeg
async def test_transcode_and_waveform(tmp_path: Path) -> None:
    source = make_recording(tmp_path / "a.webm", 1.5, streamed=True)
    target = tmp_path / "out.ogg"

    await audio.transcode_to_opus(source, target)
    peaks = await audio.waveform_peaks(target)

    assert target.read_bytes().startswith(b"OggS")
    assert abs(await audio.duration_ms(target) - 1500) <= 50
    assert len(peaks) == 64
    assert max(peaks) == 100
    assert all(0 <= peak <= 100 for peak in peaks)
