"""File-security validation for meeting uploads.

Every uploaded file is treated as hostile. Rather than raising on the first
problem, :func:`validate_upload` runs all applicable checks and returns a
structured :class:`ValidationReport` (each check pass/fail/skip with a message).
The caller decides what to do with a failing report — but it always has the full
picture, which is invaluable for debugging.

Checks: filename → extension → size → integrity (magic-byte sniff vs extension)
→ duration → virus. ``virus`` is reported as *skipped* until a scanner is wired
up. Duration/media metadata are best-effort (stdlib ``wave``; ``ffprobe`` when
present) — ffmpeg is not a hard dependency of this phase.
"""
from __future__ import annotations

import hashlib
import logging
import re
import shutil
import subprocess
import wave
from dataclasses import dataclass, field
from pathlib import PurePosixPath, PureWindowsPath

from django.conf import settings

from apps.meetings.enums import MediaKind

logger = logging.getLogger("meetingmind")

_EXT_META: dict[str, tuple[str, str]] = {
    "mp3": (MediaKind.AUDIO, "audio/mpeg"),
    "wav": (MediaKind.AUDIO, "audio/wav"),
    "m4a": (MediaKind.AUDIO, "audio/mp4"),
    "aac": (MediaKind.AUDIO, "audio/aac"),
    "flac": (MediaKind.AUDIO, "audio/flac"),
    "ogg": (MediaKind.AUDIO, "audio/ogg"),
    "mp4": (MediaKind.VIDEO, "video/mp4"),
    "mov": (MediaKind.VIDEO, "video/quicktime"),
    "avi": (MediaKind.VIDEO, "video/x-msvideo"),
    "mkv": (MediaKind.VIDEO, "video/x-matroska"),
    "webm": (MediaKind.VIDEO, "video/webm"),
}

_FTYP_BRANDS: dict[bytes, str] = {
    b"M4A ": "m4a", b"M4B ": "m4a",
    b"mp42": "mp4", b"mp41": "mp4", b"isom": "mp4", b"iso2": "mp4",
    b"iso4": "mp4", b"iso5": "mp4", b"iso6": "mp4", b"dash": "mp4", b"avc1": "mp4",
    b"qt  ": "mov",
}

_MAX_FILENAME_LEN = 255
_HEADER_BYTES = 32
_CHUNK = 1024 * 1024


@dataclass
class ValidationCheck:
    name: str
    passed: bool
    message: str = ""
    skipped: bool = False

    def as_dict(self) -> dict:
        return {"name": self.name, "passed": self.passed, "skipped": self.skipped, "message": self.message}


@dataclass
class ValidationReport:
    checks: list[ValidationCheck] = field(default_factory=list)
    # Extracted metadata (populated as checks succeed).
    original_filename: str = ""
    extension: str = ""
    media_kind: str = ""
    content_type: str = ""
    size_bytes: int = 0
    checksum_sha256: str = ""

    def add(self, name: str, passed: bool, message: str = "", *, skipped: bool = False) -> bool:
        self.checks.append(ValidationCheck(name, passed, message, skipped))
        return passed

    @property
    def ok(self) -> bool:
        return all(c.passed or c.skipped for c in self.checks)

    @property
    def first_failure(self) -> ValidationCheck | None:
        return next((c for c in self.checks if not c.passed and not c.skipped), None)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "checks": [c.as_dict() for c in self.checks],
        }


def sanitize_filename(raw: str) -> str:
    """Reduce an untrusted filename to a safe display basename (traversal-safe)."""
    name = (raw or "").strip()
    name = PurePosixPath(PureWindowsPath(name).name).name
    name = re.sub(r"[\x00-\x1f\x7f<>:\"/\\|?*]", "", name)
    name = re.sub(r"\s+", " ", name).strip().lstrip(".")
    if len(name) > _MAX_FILENAME_LEN:
        name = name[-_MAX_FILENAME_LEN:]
    return name or "upload"


def _extension_of(filename: str) -> str:
    return PurePosixPath(filename).suffix.lower().lstrip(".")


def _detect_formats(header: bytes) -> set[str]:
    fmts: set[str] = set()
    if header[4:8] == b"ftyp":
        mapped = _FTYP_BRANDS.get(header[8:12])
        if mapped:
            fmts.add(mapped)
        else:
            fmts.update({"mp4", "m4a", "mov"})
    if header[:4] == b"RIFF":
        form = header[8:12]
        if form == b"WAVE":
            fmts.add("wav")
        elif form == b"AVI ":
            fmts.add("avi")
    if header[:3] == b"ID3":
        fmts.add("mp3")
    if len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0:
        fmts.add("mp3")
        if (header[1] & 0xF6) == 0xF0:
            fmts.add("aac")
    if header[:4] == b"\x1a\x45\xdf\xa3":
        # EBML container — Matroska (.mkv) and WebM share this signature.
        fmts.update({"mkv", "webm"})
    # FLAC and Ogg (Vorbis/Opus/FLAC) native audio containers.
    if header[:4] == b"fLaC":
        fmts.add("flac")
    if header[:4] == b"OggS":
        fmts.add("ogg")
    return fmts


def validate_upload(django_file) -> ValidationReport:
    """Run all checks and return a :class:`ValidationReport` (never raises)."""
    report = ValidationReport()

    original = sanitize_filename(getattr(django_file, "name", ""))
    report.original_filename = original
    ext = _extension_of(original)
    report.extension = ext

    # 1. filename
    if not report.add("filename", bool(original) and original != "upload" or bool(ext),
                      "Filename is present." if ext else "Filename is missing or unsafe."):
        return report

    # 2. extension
    allowed = settings.ALLOWED_UPLOAD_EXTENSIONS
    if not ext:
        report.add("extension", False, "The file has no extension, so its type cannot be verified.")
        return report
    if not report.add(
        "extension", ext in allowed,
        f"'.{ext}' is allowed." if ext in allowed
        else f"Unsupported file type '.{ext}'. Allowed: {', '.join(allowed)}.",
    ):
        return report

    # 3. size
    size = int(getattr(django_file, "size", 0) or 0)
    report.size_bytes = size
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if size < settings.MIN_UPLOAD_SIZE_BYTES:
        report.add("size", False, "The file is empty or too small to be a valid recording.")
        return report
    if size > max_bytes:
        report.add("size", False,
                   f"The file is {size / 1024 / 1024:.1f} MB, exceeding the "
                   f"{settings.MAX_UPLOAD_SIZE_MB} MB limit.")
        return report
    report.add("size", True, f"{size / 1024 / 1024:.2f} MB is within limits.")

    # 4. integrity — magic-byte sniff must agree with the extension
    django_file.seek(0)
    header = django_file.read(_HEADER_BYTES)
    django_file.seek(0)
    detected = _detect_formats(header)
    if not detected:
        report.add("integrity", False,
                   "The file does not look like a supported recording (corrupted or disguised).")
        return report
    if ext not in detected:
        report.add("integrity", False,
                   f"The file contents do not match its '.{ext}' extension.")
        return report
    report.add("integrity", True, "File signature matches its extension.")

    media_kind, content_type = _EXT_META[ext]
    report.media_kind = media_kind
    report.content_type = content_type
    report.checksum_sha256 = _compute_checksum(django_file)

    # 5. duration — best-effort; skipped when it can't be determined here
    report.add("duration", True, "Duration is validated after storage.", skipped=True)

    # 6. virus — placeholder until a scanner is configured
    report.add("virus", True, "Virus scanning is not configured.", skipped=True)

    return report


def _compute_checksum(django_file) -> str:
    django_file.seek(0)
    digest = hashlib.sha256()
    for chunk in django_file.chunks(chunk_size=_CHUNK):
        digest.update(chunk)
    django_file.seek(0)
    return digest.hexdigest()


def probe_duration_seconds(path: str, extension: str) -> int | None:
    """Best-effort duration in whole seconds (WAV via stdlib, else ffprobe). Never raises."""
    try:
        if extension == "wav":
            with wave.open(path, "rb") as wav:
                rate = wav.getframerate() or 0
                if rate:
                    return int(round(wav.getnframes() / rate))
    except Exception:  # noqa: BLE001
        logger.debug("WAV duration probe failed for %s", path, exc_info=True)

    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        try:
            out = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True, timeout=30, check=True,
            )
            if out.stdout.strip():
                return int(round(float(out.stdout.strip())))
        except Exception:  # noqa: BLE001
            logger.debug("ffprobe duration probe failed for %s", path, exc_info=True)
    return None


def probe_media_metadata(path: str, extension: str) -> dict:
    """Best-effort technical media properties. Returns a dict (possibly partial).

    WAV yields channels/sample_rate/container from the stdlib. Richer probing
    (codecs, bitrate, frame rate) arrives with ffprobe in a later phase.
    """
    meta: dict = {"container": extension}
    try:
        if extension == "wav":
            with wave.open(path, "rb") as wav:
                meta["channels"] = wav.getnchannels()
                meta["sample_rate"] = wav.getframerate()
                meta["audio_codec"] = "pcm_s16le" if wav.getsampwidth() == 2 else "pcm"
                meta["bitrate"] = (
                    wav.getframerate() * wav.getnchannels() * wav.getsampwidth() * 8
                )
    except Exception:  # noqa: BLE001
        logger.debug("WAV metadata probe failed for %s", path, exc_info=True)
    return meta
