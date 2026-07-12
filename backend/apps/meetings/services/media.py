"""FFmpeg-backed media services: inspection, extraction, normalization.

Each service is production-ready and self-contained. When ffmpeg/ffprobe are not
installed, they fail with a structured :class:`ProcessingError` (or, for
inspection, degrade to a stdlib fallback) — never a raw traceback. Temp files are
the caller's to clean up; the original upload is never modified.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
import wave
from dataclasses import dataclass, field

from django.conf import settings

logger = logging.getLogger("meetingmind.processing")


class ProcessingError(Exception):
    """A structured processing failure surfaced to the pipeline/job engine."""

    def __init__(self, message: str, *, code: str = "processing_error", retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable


@dataclass
class MediaInfo:
    container: str = ""
    duration_seconds: float | None = None
    audio_codec: str = ""
    video_codec: str = ""
    bitrate: int | None = None
    sample_rate: int | None = None
    channels: int | None = None
    frame_rate: float | None = None
    width: int | None = None
    height: int | None = None
    has_audio: bool = False
    extra: dict = field(default_factory=dict)

    def as_metadata(self) -> dict:
        """Fields matching the MediaMetadata columns."""
        return {
            "container": self.container[:32],
            "audio_codec": self.audio_codec[:32],
            "video_codec": self.video_codec[:32],
            "bitrate": self.bitrate,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "frame_rate": self.frame_rate,
            "width": self.width,
            "height": self.height,
        }


def ffmpeg_available() -> bool:
    return shutil.which(settings.FFMPEG_BINARY) is not None


def ffprobe_available() -> bool:
    return shutil.which(settings.FFPROBE_BINARY) is not None


def _run(cmd: list[str], *, timeout: int = 600) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=True)
    except FileNotFoundError as exc:
        raise ProcessingError(f"{cmd[0]} is not installed.", code="ffmpeg_missing", retryable=False) from exc
    except subprocess.TimeoutExpired as exc:
        raise ProcessingError("Media processing timed out.", code="timeout", retryable=True) from exc
    except subprocess.CalledProcessError as exc:
        tail = (exc.stderr or "").strip().splitlines()[-1:] or [""]
        raise ProcessingError(
            f"{cmd[0]} failed: {tail[0]}", code="ffmpeg_error", retryable=False
        ) from exc


def _parse_fraction(value: str | None) -> float | None:
    if not value or value in {"0/0", "N/A"}:
        return None
    try:
        if "/" in value:
            num, den = value.split("/")
            den_f = float(den)
            return round(float(num) / den_f, 3) if den_f else None
        return float(value)
    except (ValueError, ZeroDivisionError):
        return None


class MediaInspectionService:
    """Detect container/codec/duration/sample-rate/channels/bitrate/resolution/fps."""

    def inspect(self, path: str) -> MediaInfo:
        if ffprobe_available():
            return self._inspect_ffprobe(path)
        logger.info("ffprobe unavailable — using stdlib media inspection fallback.")
        return self._inspect_fallback(path)

    def _inspect_ffprobe(self, path: str) -> MediaInfo:
        out = _run([
            settings.FFPROBE_BINARY, "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", path,
        ], timeout=60)
        data = json.loads(out.stdout or "{}")
        fmt = data.get("format", {})
        info = MediaInfo(
            container=(fmt.get("format_name", "") or "").split(",")[0],
            duration_seconds=float(fmt["duration"]) if fmt.get("duration") else None,
            bitrate=int(fmt["bit_rate"]) if fmt.get("bit_rate") else None,
        )
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "audio":
                info.has_audio = True
                info.audio_codec = stream.get("codec_name", "")
                info.sample_rate = int(stream["sample_rate"]) if stream.get("sample_rate") else info.sample_rate
                info.channels = stream.get("channels", info.channels)
            elif stream.get("codec_type") == "video":
                info.video_codec = stream.get("codec_name", "")
                info.width = stream.get("width", info.width)
                info.height = stream.get("height", info.height)
                info.frame_rate = _parse_fraction(stream.get("avg_frame_rate")) or info.frame_rate
        return info

    def _inspect_fallback(self, path: str) -> MediaInfo:
        info = MediaInfo(extra={"inspection": "stdlib-fallback"})
        try:
            if path.lower().endswith(".wav"):
                with wave.open(path, "rb") as w:
                    info.container = "wav"
                    info.audio_codec = "pcm_s16le" if w.getsampwidth() == 2 else "pcm"
                    info.sample_rate = w.getframerate()
                    info.channels = w.getnchannels()
                    info.has_audio = True
                    if w.getframerate():
                        info.duration_seconds = round(w.getnframes() / w.getframerate(), 3)
                        info.bitrate = w.getframerate() * w.getnchannels() * w.getsampwidth() * 8
        except Exception:  # noqa: BLE001 — inspection is best-effort
            logger.debug("stdlib inspection failed for %s", path, exc_info=True)
        return info


class AudioExtractionService:
    """Extract the audio stream from any container to a temporary PCM WAV."""

    def extract(self, src_path: str) -> str:
        if not ffmpeg_available():
            raise ProcessingError(
                "FFmpeg is required to extract audio but is not installed.",
                code="ffmpeg_missing", retryable=False,
            )
        dst = tempfile.NamedTemporaryFile(suffix=".extracted.wav", delete=False)
        dst.close()
        _run([
            settings.FFMPEG_BINARY, "-y", "-i", src_path,
            "-vn", "-acodec", "pcm_s16le", dst.name,
        ])
        return dst.name


class AudioNormalizationService:
    """Normalize audio to Whisper's preferred 16 kHz mono PCM WAV."""

    def normalize(self, src_path: str, *, sample_rate: int | None = None) -> str:
        if not ffmpeg_available():
            raise ProcessingError(
                "FFmpeg is required to normalize audio but is not installed.",
                code="ffmpeg_missing", retryable=False,
            )
        rate = sample_rate or settings.NORMALIZED_SAMPLE_RATE
        dst = tempfile.NamedTemporaryFile(suffix=".norm.wav", delete=False)
        dst.close()
        _run([
            settings.FFMPEG_BINARY, "-y", "-i", src_path,
            "-ac", "1", "-ar", str(rate), "-acodec", "pcm_s16le", dst.name,
        ])
        return dst.name
