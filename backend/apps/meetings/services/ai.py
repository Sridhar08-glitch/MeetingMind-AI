"""AI summarization orchestration (provider-agnostic).

Produces ALL meeting artifacts in a single structured JSON inference per chunk
(faster + internally consistent), validating and normalizing every response and
retrying once before recording a structured ProcessingError. Long transcripts are
chunked with overlap and merged.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from django.conf import settings

from apps.meetings.prompts import ANALYSIS_VERSION, analysis_schema, prompt_registry
from apps.meetings.services.chunking import chunk_text
from apps.meetings.services.llm import LLMError, get_llm_provider
from apps.meetings.services.media import ProcessingError

logger = logging.getLogger("meetingmind.ai")

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


class AIValidationError(Exception):
    """The LLM response could not be parsed/validated into the analysis schema."""


@dataclass
class AnalysisResult:
    parsed: dict
    raw_response: str
    model: str
    provider: str
    prompt_version: str
    inference_ms: int
    chunks: int = 1
    metadata: dict = field(default_factory=dict)


# --- normalization ----------------------------------------------------------
def _as_str_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _as_dict_list(value, keys: list[str]) -> list[dict]:
    out: list[dict] = []
    if not isinstance(value, list):
        return out
    for item in value:
        if isinstance(item, dict):
            row = {}
            for k in keys:
                v = item.get(k, [] if k == "participants" else "")
                row[k] = _as_str_list(v) if k == "participants" else (str(v).strip() if v is not None else "")
            if any(row[k] for k in keys):
                out.append(row)
        elif isinstance(item, str) and item.strip():
            out.append({keys[0]: item.strip(), **{k: "" for k in keys[1:]}})
    return out


def _as_keywords(value) -> dict:
    buckets = ["topics", "technologies", "people", "companies", "phrases"]
    if not isinstance(value, dict):
        return {b: [] for b in buckets}
    return {b: _as_str_list(value.get(b)) for b in buckets}


def validate_analysis(obj) -> dict:
    """Normalize a raw LLM object into the canonical analysis structure.

    Coerces types and fills defaults so minor model deviations are tolerated, but
    raises :class:`AIValidationError` if the response is unusable (no summary).
    """
    if not isinstance(obj, dict):
        raise AIValidationError("response is not a JSON object")
    out = {
        "executive_summary": str(obj.get("executive_summary", "")).strip(),
        "detailed_summary": str(obj.get("detailed_summary", "")).strip(),
        "bullet_summary": _as_str_list(obj.get("bullet_summary")),
        "meeting_minutes": str(obj.get("meeting_minutes", "")).strip(),
        "action_items": _as_dict_list(obj.get("action_items"), ["task", "owner", "priority", "due_date", "status"]),
        "decisions": _as_dict_list(obj.get("decisions"), ["decision", "reason", "participants"]),
        "risks": _as_dict_list(obj.get("risks"), ["risk", "severity", "mitigation"]),
        "issues": _as_dict_list(obj.get("issues"), ["title", "type", "severity", "description"]),
        "follow_ups": _as_dict_list(obj.get("follow_ups"), ["item", "owner"]),
        "deadlines": _as_dict_list(obj.get("deadlines"), ["item", "date"]),
        "keywords": _as_keywords(obj.get("keywords")),
    }
    if not out["executive_summary"] and not out["detailed_summary"]:
        raise AIValidationError("no summary produced")
    return out


def _extract_json(text: str) -> str:
    match = _JSON_RE.search(text or "")
    if not match:
        raise AIValidationError("no JSON object found in response")
    return match.group(0)


_KEYWORD_BUCKETS = ["topics", "technologies", "people", "companies", "phrases"]


def _excerpt(text: str, *, max_chars: int = 500) -> str:
    """A short leading excerpt, ending on a sentence boundary where possible."""
    text = " ".join((text or "").split())
    if not text:
        return "An automatic summary could not be generated for this recording."
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    for sep in (". ", "? ", "! "):
        idx = cut.rfind(sep)
        if idx > max_chars * 0.5:
            return cut[: idx + 1].strip()
    return cut.rstrip() + "…"


def fallback_parsed(transcript_text: str) -> dict:
    """A deterministic, no-LLM analysis for when the model can't produce valid
    JSON. Keeps a good transcript usable (summary excerpt + empty structured
    fields) instead of failing the whole meeting."""
    return {
        "executive_summary": _excerpt(transcript_text),
        "detailed_summary": "",
        "bullet_summary": [],
        "meeting_minutes": "",
        "action_items": [], "decisions": [], "risks": [], "issues": [],
        "follow_ups": [], "deadlines": [],
        "keywords": {b: [] for b in _KEYWORD_BUCKETS},
    }


def _language_instruction(output_language: str | None) -> str:
    """Prompt fragment forcing AI output into a target language (empty = source)."""
    if not output_language or output_language in ("original", "source"):
        return ""
    from apps.meetings.services.stt.languages import language_name

    return f"Write ALL string values in the JSON in {language_name(output_language)}. "


class AISummarizationService:
    def __init__(self, provider=None, *, model: str | None = None):
        self.provider = provider or get_llm_provider(model=model)

    @property
    def provider_name(self) -> str:
        return self.provider.name

    @property
    def model_name(self) -> str:
        return self.provider.model_name

    def analyze(
        self, transcript_text: str, *, style: str | None = None, output_language: str | None = None
    ) -> AnalysisResult:
        style = style or settings.AI_SUMMARY_STYLE
        chunks = chunk_text(transcript_text)
        if not chunks:
            raise ProcessingError("Transcript is empty; nothing to summarize.",
                                  code="empty_transcript", retryable=False)

        raw_parts: list[str] = []
        parsed_parts: list[dict] = []
        total_ms = 0
        for chunk in chunks:
            parsed, raw, ms = self._analyze_chunk(chunk, style, output_language)
            parsed_parts.append(parsed)
            raw_parts.append(raw)
            total_ms += ms

        if len(parsed_parts) == 1:
            merged = parsed_parts[0]
        else:
            merged, ms = self._merge(parsed_parts, style)
            total_ms += ms

        return AnalysisResult(
            parsed=merged,
            raw_response="\n---\n".join(raw_parts),
            model=self.model_name,
            provider=self.provider_name,
            prompt_version=ANALYSIS_VERSION,
            inference_ms=total_ms,
            chunks=len(chunks),
        )

    def fallback(self, transcript_text: str) -> AnalysisResult:
        """A deterministic result when the LLM can't summarize this transcript,
        so the meeting still completes with its transcript rather than failing."""
        return AnalysisResult(
            parsed=fallback_parsed(transcript_text),
            raw_response="",
            model=self.model_name,
            provider=self.provider_name,
            prompt_version=ANALYSIS_VERSION,
            inference_ms=0,
            chunks=0,
            metadata={"fallback": True},
        )

    # --- one structured inference per chunk, validate + retry once ----------
    def _analyze_chunk(self, chunk: str, style: str, output_language: str | None = None) -> tuple[dict, str, int]:
        prompt = prompt_registry.get("meeting_analysis")
        system, user = prompt.render(
            schema=analysis_schema(), style=style, transcript=chunk,
            language_instruction=_language_instruction(output_language),
        )
        last_error: Exception | None = None
        total_ms = 0
        for attempt in (1, 2):
            sys_prompt = system if attempt == 1 else (
                system + " Your previous reply was not valid JSON. Reply with ONE valid JSON object only."
            )
            try:
                resp = self.provider.generate(user, system=sys_prompt, json=True, schema_hint="meeting_analysis")
            except LLMError as exc:
                raise ProcessingError(f"LLM request failed: {exc.message}",
                                      code="llm_error", retryable=exc.retryable) from exc
            total_ms += resp.inference_ms
            try:
                parsed = validate_analysis(json.loads(_extract_json(resp.text)))
                return parsed, resp.text, total_ms
            except (json.JSONDecodeError, AIValidationError) as exc:
                last_error = exc
                logger.warning("AI JSON validation failed (attempt %s): %s", attempt, exc)
        raise ProcessingError(
            f"LLM did not return valid JSON after retry: {last_error}",
            code="ai_invalid_json", retryable=False,
        )

    def _merge(self, parts: list[dict], style: str) -> tuple[dict, int]:
        """Merge per-chunk analyses. Programmatic union of lists + LLM-consolidated
        summaries (with a safe programmatic fallback)."""
        merged = {
            "action_items": _dedup(sum((p["action_items"] for p in parts), []), "task"),
            "decisions": _dedup(sum((p["decisions"] for p in parts), []), "decision"),
            "risks": _dedup(sum((p["risks"] for p in parts), []), "risk"),
            "issues": _dedup(sum((p["issues"] for p in parts), []), "title"),
            "follow_ups": _dedup(sum((p["follow_ups"] for p in parts), []), "item"),
            "deadlines": _dedup(sum((p["deadlines"] for p in parts), []), "item"),
            "keywords": _merge_keywords([p["keywords"] for p in parts]),
            "bullet_summary": _dedup_str(sum((p["bullet_summary"] for p in parts), [])),
        }
        total_ms = 0
        try:
            prompt = prompt_registry.get("merge_analysis")
            partials = "\n".join(json.dumps({k: p[k] for k in
                ("executive_summary", "detailed_summary", "meeting_minutes")}) for p in parts)
            system, user = prompt.render(schema=analysis_schema(), partials=partials)
            resp = self.provider.generate(user, system=system, json=True, schema_hint="meeting_analysis")
            total_ms = resp.inference_ms
            consolidated = validate_analysis(json.loads(_extract_json(resp.text)))
            merged["executive_summary"] = consolidated["executive_summary"]
            merged["detailed_summary"] = consolidated["detailed_summary"]
            merged["meeting_minutes"] = consolidated["meeting_minutes"]
        except Exception:  # noqa: BLE001 — fall back to the first chunk's summaries
            logger.warning("Summary merge failed; using first-chunk summaries.", exc_info=True)
            merged["executive_summary"] = parts[0]["executive_summary"]
            merged["detailed_summary"] = "\n\n".join(p["detailed_summary"] for p in parts if p["detailed_summary"])
            merged["meeting_minutes"] = parts[0]["meeting_minutes"]
        return merged, total_ms


def _dedup(rows: list[dict], key: str) -> list[dict]:
    seen, out = set(), []
    for r in rows:
        k = (r.get(key) or "").lower().strip()
        if k and k not in seen:
            seen.add(k)
            out.append(r)
    return out


def _dedup_str(items: list[str]) -> list[str]:
    seen, out = set(), []
    for i in items:
        k = i.lower().strip()
        if k and k not in seen:
            seen.add(k)
            out.append(i)
    return out


def _merge_keywords(kw_list: list[dict]) -> dict:
    buckets = ["topics", "technologies", "people", "companies", "phrases"]
    return {b: _dedup_str(sum((kw.get(b, []) for kw in kw_list), [])) for b in buckets}
