"""Serialize a transcript to downloadable formats: TXT, Markdown, JSON, SRT, VTT."""
from __future__ import annotations

import json

# format -> (mime type, file extension)
FORMATS = {
    "txt": ("text/plain; charset=utf-8", "txt"),
    "md": ("text/markdown; charset=utf-8", "md"),
    "json": ("application/json", "json"),
    "srt": ("application/x-subrip; charset=utf-8", "srt"),
    "vtt": ("text/vtt; charset=utf-8", "vtt"),
}


def _ts(seconds: float, *, comma: bool) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    sep = "," if comma else "."
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _speaker_prefix(seg) -> str:
    return f"{seg.speaker}: " if seg.speaker else ""


def to_txt(meeting, transcript, segments) -> str:
    lines = [f"{_speaker_prefix(s)}{s.text}" for s in segments]
    return "\n".join(lines) + ("\n" if lines else "")


def to_markdown(meeting, transcript, segments) -> str:
    out = [f"# {meeting.title}", ""]
    if transcript:
        out += [
            f"- **Language:** {transcript.detected_language or '—'}",
            f"- **Words:** {transcript.word_count}",
            f"- **Model:** {transcript.model_used or '—'}",
            "",
        ]
    for s in segments:
        stamp = _ts(s.start_time, comma=False)[:8]
        out.append(f"**[{stamp}]** {_speaker_prefix(s)}{s.text}")
    return "\n".join(out) + "\n"


def to_json(meeting, transcript, segments) -> str:
    payload = {
        "title": meeting.title,
        "language": transcript.detected_language if transcript else "",
        "model": transcript.model_used if transcript else "",
        "word_count": transcript.word_count if transcript else 0,
        "avg_confidence": transcript.avg_confidence if transcript else None,
        "segments": [
            {
                "index": s.index, "start": s.start_time, "end": s.end_time,
                "speaker": s.speaker, "text": s.text, "confidence": s.confidence,
            }
            for s in segments
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def to_srt(meeting, transcript, segments) -> str:
    blocks = []
    for i, s in enumerate(segments, start=1):
        blocks.append(
            f"{i}\n{_ts(s.start_time, comma=True)} --> {_ts(s.end_time, comma=True)}\n"
            f"{_speaker_prefix(s)}{s.text}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def to_vtt(meeting, transcript, segments) -> str:
    out = ["WEBVTT", ""]
    for s in segments:
        out.append(f"{_ts(s.start_time, comma=False)} --> {_ts(s.end_time, comma=False)}")
        out.append(f"{_speaker_prefix(s)}{s.text}")
        out.append("")
    return "\n".join(out)


_RENDERERS = {
    "txt": to_txt, "md": to_markdown, "json": to_json, "srt": to_srt, "vtt": to_vtt,
}


def render(fmt: str, meeting, transcript, segments) -> tuple[str, str, str]:
    """Return (content, mime_type, extension) for the requested format."""
    fmt = (fmt or "txt").lower()
    if fmt not in _RENDERERS:
        raise ValueError(f"Unsupported format '{fmt}'. Choose one of: {', '.join(FORMATS)}.")
    mime, ext = FORMATS[fmt]
    return _RENDERERS[fmt](meeting, transcript, segments), mime, ext
