"""MeetingMind AI — REAL demo media generation (100% local, no cloud).

Turns each scripted demo meeting (see :mod:`apps.common.demo_data`) into a real
media file the demo user can actually upload and watch process:

  * audio meetings → a ``.wav`` recording (16 kHz mono),
  * video meetings → an ``.mp4`` (a rendered title card looped over the audio).

Speech is synthesised with the local Windows SAPI engine (via
``scripts/tts_synthesize.ps1``); the container work is done with the portable
ffmpeg configured in settings. Nothing here contacts a paid API.

Files land in ``backend/demo_media/`` and are cached — regeneration is skipped
when a file already exists (pass ``force=True`` to rebuild). A ``manifest.json``
records the mapping so the seeder and the sample-file picker can find them.

Entry point: :func:`generate_all`.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings

from apps.common import demo_data
from apps.common.demo_data import MEETINGS, MeetingSpec

logger = logging.getLogger("meetingmind")

MEDIA_DIR = Path(settings.BASE_DIR) / "demo_media"
MANIFEST_PATH = MEDIA_DIR / "manifest.json"
_PS_SCRIPT = Path(settings.BASE_DIR) / "scripts" / "tts_synthesize.ps1"

_CARD_W, _CARD_H = 1280, 720
_FONTS = [
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
]
_MTYPE_LABEL = {
    "sprint_planning": "Sprint Planning",
    "standup": "Standup",
    "sales_call": "Sales Call",
    "customer_interview": "Customer Interview",
    "executive": "Executive Review",
    "design_review": "Design Review",
}


def _ffmpeg() -> str:
    return shutil.which(settings.FFMPEG_BINARY) or settings.FFMPEG_BINARY


def _powershell() -> str:
    return shutil.which("powershell") or "powershell"


def _run(cmd: list, *, timeout: int = 900) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(
            f"command failed ({proc.returncode}): {cmd[0]}\n{proc.stderr[-1500:]}"
        )


# ─────────────────────────── speech synthesis ───────────────────────────
def _synthesize_wav(spec: MeetingSpec, out_wav: Path) -> None:
    """Synthesise the meeting's scripted lines into a single raw WAV via SAPI."""
    voices = demo_data.speaker_voices(spec)
    payload = {
        "out": str(out_wav),
        "lines": [
            {"voice": voices[sp][0], "rate": voices[sp][1], "text": text}
            for sp, text in demo_data.build_script_lines(spec)
        ],
    }
    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8"
    ) as fh:
        json.dump(payload, fh)
        spec_path = fh.name
    try:
        _run([
            _powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(_PS_SCRIPT), "-Spec", spec_path,
        ], timeout=600)
    finally:
        Path(spec_path).unlink(missing_ok=True)
    if not out_wav.exists() or out_wav.stat().st_size < 1024:
        raise RuntimeError(f"TTS produced no audio for '{spec.title}'")


# ─────────────────────────── title card (video) ───────────────────────────
def _render_card(spec: MeetingSpec, out_png: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    def font(size: int):
        for path in _FONTS:
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
        return ImageFont.load_default()

    img = Image.new("RGB", (_CARD_W, _CARD_H), (11, 18, 32))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, _CARD_W, 8], fill=(59, 130, 246))  # accent bar

    def center(text: str, f, y: int, fill):
        w = d.textlength(text, font=f)
        d.text(((_CARD_W - w) / 2, y), text, font=f, fill=fill)

    subtitle = f"{_MTYPE_LABEL.get(spec.mtype, spec.mtype)}   |   {spec.project}"
    center(spec.title, font(56), 285, (255, 255, 255))
    center(subtitle, font(30), 372, (140, 160, 192))
    center("MeetingMind AI  ·  demo recording", font(24), 650, (90, 110, 140))
    img.save(out_png)


# ─────────────────────────── container assembly ───────────────────────────
def _finalize_audio(raw_wav: Path, out_wav: Path) -> None:
    _run([
        _ffmpeg(), "-y", "-loglevel", "error", "-i", str(raw_wav),
        "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(out_wav),
    ])


def _finalize_video(raw_wav: Path, card_png: Path, out_mp4: Path) -> None:
    _run([
        _ffmpeg(), "-y", "-loglevel", "error",
        "-loop", "1", "-i", str(card_png), "-i", str(raw_wav),
        "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
        "-r", "12", "-c:a", "aac", "-b:a", "128k", "-shortest", str(out_mp4),
    ])


def _probe_duration(path: Path) -> float:
    probe = shutil.which(settings.FFPROBE_BINARY) or settings.FFPROBE_BINARY
    try:
        out = subprocess.run(
            [probe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        return round(float(out.stdout.strip()), 2)
    except Exception:  # noqa: BLE001
        return 0.0


# ─────────────────────────── orchestration ───────────────────────────
def generate_one(index: int, spec: MeetingSpec, *, force: bool = False, log=print) -> dict:
    """Generate (or reuse) the media file for one meeting; return a manifest row."""
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    filename = demo_data.media_filename(index, spec)
    out_path = MEDIA_DIR / filename

    if out_path.exists() and not force:
        log(f"  = {filename}  (cached)")
        return _manifest_row(index, spec, out_path)

    tmp = MEDIA_DIR / f".tmp_{index:02d}.wav"
    try:
        _synthesize_wav(spec, tmp)
        if spec.media == "video":
            card = MEDIA_DIR / f".tmp_{index:02d}.png"
            try:
                _render_card(spec, card)
                _finalize_video(tmp, card, out_path)
            finally:
                card.unlink(missing_ok=True)
        else:
            _finalize_audio(tmp, out_path)
    finally:
        tmp.unlink(missing_ok=True)

    row = _manifest_row(index, spec, out_path)
    log(f"  + {filename}  [{spec.media}, {row['duration_seconds']}s, {row['size_bytes'] // 1024} KB]")
    return row


def _manifest_row(index: int, spec: MeetingSpec, path: Path) -> dict:
    return {
        "index": index,
        "title": spec.title,
        "project": spec.project,
        "mtype": spec.mtype,
        "media": spec.media,
        "filename": path.name,
        "content_type": "video/mp4" if spec.media == "video" else "audio/wav",
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "duration_seconds": _probe_duration(path) if path.exists() else 0.0,
    }


def generate_all(*, force: bool = False, log=print) -> list[dict]:
    """Generate all demo media files and write the manifest. Returns manifest rows."""
    if not _PS_SCRIPT.exists():
        raise RuntimeError(f"TTS script missing: {_PS_SCRIPT}")
    rows = [generate_one(i, spec, force=force, log=log) for i, spec in enumerate(MEETINGS)]
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    log(f"  manifest: {MANIFEST_PATH}")
    return rows


def load_manifest() -> list[dict]:
    """Return the media manifest (empty list if media hasn't been generated)."""
    if not MANIFEST_PATH.exists():
        return []
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def media_path(filename: str) -> Path | None:
    """Resolve a manifest filename to an on-disk path, guarding against traversal."""
    candidate = (MEDIA_DIR / filename).resolve()
    if candidate.parent != MEDIA_DIR.resolve() or not candidate.exists():
        return None
    return candidate
