"""AI speaker name suggestions (Phase 15) — SUGGEST ONLY, never auto-apply.

Reads the speaker-labeled transcript and, only where a name is clearly supported
(a self-introduction or direct address), stores a `suggested_name` +
`suggested_confidence` on the Speaker. The user must confirm before anything is
renamed. Best-effort: never fails the meeting.
"""
from __future__ import annotations

import json
import logging
import re

from apps.meetings.models import Speaker, TranscriptSegment
from apps.meetings.prompts import SPEAKER_NAMING_VERSION, prompt_registry
from apps.meetings.services.llm import LLMError, get_llm_provider

logger = logging.getLogger("meetingmind.ai")

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_MAX_CHARS = 8000  # cap the transcript sent to the model


def build_labeled_transcript(meeting, *, use_names: bool = False, limit: int = _MAX_CHARS) -> str:
    """A `Speaker N: text` transcript for the LLM (or downstream AI attribution)."""
    segs = (
        TranscriptSegment.objects.filter(meeting=meeting)
        .select_related("speaker_ref").order_by("index")
    )
    lines: list[str] = []
    total = 0
    for seg in segs:
        sp = seg.speaker_ref
        label = (sp.name if (use_names and sp) else (sp.label if sp else seg.speaker)) or "Speaker"
        line = f"{label}: {seg.text}"
        total += len(line)
        if total > limit:
            break
        lines.append(line)
    return "\n".join(lines)


def suggest_speaker_names(meeting, *, llm=None) -> int:
    """Populate `suggested_name`/`suggested_confidence` on the meeting's speakers.

    Returns the number of suggestions written. Never raises.
    """
    speakers = list(Speaker.objects.filter(meeting=meeting))
    if len(speakers) < 1:
        return 0
    by_label = {s.label: s for s in speakers}
    transcript = build_labeled_transcript(meeting)
    if not transcript.strip():
        return 0

    provider = llm or get_llm_provider()
    prompt = prompt_registry.get("speaker_naming", SPEAKER_NAMING_VERSION)
    system, user = prompt.render(transcript=transcript)
    try:
        resp = provider.generate(user, system=system, json=True, schema_hint="speaker_naming")
    except LLMError as exc:
        logger.warning("Speaker naming LLM failed: %s", exc.message)
        return 0

    try:
        obj = json.loads(_JSON_RE.search(resp.text or "").group(0))
        items = obj.get("speakers", []) if isinstance(obj, dict) else []
    except (json.JSONDecodeError, AttributeError):
        logger.warning("Speaker naming returned invalid JSON; no suggestions.")
        return 0

    written = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        sp = by_label.get(str(item.get("label", "")).strip())
        name = str(item.get("name", "")).strip()
        if not sp or not name:
            continue
        try:
            conf = float(item.get("confidence", 0))
        except (TypeError, ValueError):
            conf = 0.0
        sp.suggested_name = name[:120]
        sp.suggested_confidence = max(0.0, min(100.0, conf))
        sp.save(update_fields=["suggested_name", "suggested_confidence", "updated_at"])
        written += 1
    return written
