"""Meeting-processing pipeline (Phase 6): real local Speech-to-Text.

Stages run on the existing engine/registry/context. Real work now happens:
inspect media, extract + normalize audio (ffmpeg), transcribe with the configured
provider (Faster-Whisper in production, DummySpeechProvider in dev), clean +
segment, and store an editable transcript. AI stages (summary/keywords/actions)
are Phase 7 and intentionally absent here.

Provider selection is config-only; stages never know which provider is active.
Missing ffmpeg surfaces as a structured, non-retryable ProcessingError.
"""
from __future__ import annotations

import logging
import os
import time


from apps.jobs.pipeline import (
    NonRetryableStageError,
    PipelineDefinition,
    Stage,
    StageError,
    StageResult,
    register_pipeline,
    register_stage,
)
from apps.meetings.services.media import (
    AudioExtractionService,
    AudioNormalizationService,
    MediaInspectionService,
    ProcessingError,
    ffmpeg_available,
)
from apps.meetings.services.transcription import (
    SpeechToTextService,
    TranscriptCleanupService,
    TranscriptSegmentationService,
)

logger = logging.getLogger("meetingmind.processing")


def _raise_stage(exc: ProcessingError):
    """Convert a structured ProcessingError into the right engine exception."""
    if exc.retryable:
        raise StageError(exc.message) from exc
    raise NonRetryableStageError(exc.message) from exc


class MeetingStage(Stage):
    """Base stage: resolves meeting + current file + source path into context."""

    def meeting(self, ctx):
        m = ctx.get("meeting")
        if m is None:
            from apps.meetings.models import Meeting

            m = Meeting.objects.filter(id=ctx.payload.get("meeting_id")).first()
            ctx.set("meeting", m)
        return m

    def current_file(self, ctx):
        cf = ctx.get("current_file")
        if cf is None:
            meeting = self.meeting(ctx)
            cf = meeting.current_file if meeting else None
            ctx.set("current_file", cf)
        return cf

    def source_path(self, ctx) -> str | None:
        cf = self.current_file(ctx)
        if cf is None or not cf.file:
            return None
        return ctx.storage.path(cf.file.name)

    def _register_temp(self, ctx, path: str | None) -> None:
        if path:
            ctx.shared.setdefault("temp_files", []).append(path)


@register_stage
class ValidationStage(MeetingStage):
    key = "validation"
    name = "Validation"
    retryable = False

    def run(self, ctx) -> StageResult:
        meeting = self.meeting(ctx)
        if meeting is None:
            raise NonRetryableStageError("Meeting not found.")
        cf = self.current_file(ctx)
        if cf is None or not cf.checksum_sha256:
            raise NonRetryableStageError("No verified file to process.")
        return StageResult(message=f"file v{cf.version} verified")


@register_stage
class MediaInspectionStage(MeetingStage):
    key = "media_inspection"
    name = "Media Inspection"
    retryable = False

    def run(self, ctx) -> StageResult:
        from apps.meetings.models import MediaMetadata

        cf = self.current_file(ctx)
        path = self.source_path(ctx)
        if not path or not os.path.exists(path):
            raise NonRetryableStageError("Source media file is missing from storage.")
        try:
            info = MediaInspectionService().inspect(path)
        except ProcessingError as exc:
            _raise_stage(exc)

        MediaMetadata.objects.update_or_create(file=cf, defaults=info.as_metadata())
        if info.duration_seconds:
            ctx.set("duration", info.duration_seconds)
            meeting = self.meeting(ctx)
            if not meeting.duration_seconds:
                meeting.duration_seconds = int(round(info.duration_seconds))
                meeting.save(update_fields=["duration_seconds", "updated_at"])
        ctx.set("media_info", info)
        return StageResult(message=f"{info.container or 'media'} inspected", data=info.as_metadata())


@register_stage
class AudioExtractionStage(MeetingStage):
    key = "audio_extraction"
    name = "Audio Extraction"
    retryable = False

    def run(self, ctx) -> StageResult:
        # Only real (audio-requiring) providers need extraction; the dummy
        # provider transcribes without audio.
        if not SpeechToTextService().requires_audio:
            return StageResult(skipped=True, message="dummy provider — no extraction needed")
        # ffmpeg CLI is an optimization: Faster-Whisper decodes the source
        # directly via bundled PyAV, so if the CLI is absent we skip and let the
        # STT step read the original file. Genuine ffmpeg *errors* still fail.
        if not ffmpeg_available():
            return StageResult(skipped=True, message="ffmpeg CLI not installed — provider decodes source directly")
        try:
            extracted = AudioExtractionService().extract(self.source_path(ctx))
        except ProcessingError as exc:
            _raise_stage(exc)
        self._register_temp(ctx, extracted)
        ctx.set("extracted_audio", extracted)
        return StageResult(message="audio extracted")


@register_stage
class AudioNormalizationStage(MeetingStage):
    key = "audio_normalization"
    name = "Audio Normalization"
    retryable = False

    def run(self, ctx) -> StageResult:
        if not SpeechToTextService().requires_audio:
            return StageResult(skipped=True, message="dummy provider — no normalization needed")
        if not ffmpeg_available():
            # Faster-Whisper resamples to 16 kHz mono internally (via PyAV).
            return StageResult(skipped=True, message="ffmpeg CLI not installed — provider normalizes internally")
        source = ctx.get("extracted_audio") or self.source_path(ctx)
        try:
            normalized = AudioNormalizationService().normalize(source)
        except ProcessingError as exc:
            _raise_stage(exc)
        self._register_temp(ctx, normalized)
        ctx.set("audio_path", normalized)
        return StageResult(message="normalized to 16 kHz mono")


@register_stage
class LanguageDetectionStage(MeetingStage):
    key = "language_detection"
    name = "Language Detection"

    def run(self, ctx) -> StageResult:
        # Explicit override (payload/meeting) wins; otherwise the STT step
        # auto-detects and reports the language.
        override = ctx.payload.get("language") or ""
        meeting = self.meeting(ctx)
        hint = override or (meeting.language if meeting and meeting.language != "en" else None)
        ctx.set("language_hint", hint)
        return StageResult(message=f"language hint: {hint or 'auto-detect'}")


@register_stage
class SpeechToTextStage(MeetingStage):
    key = "speech_to_text"
    name = "Speech to Text"

    def run(self, ctx) -> StageResult:
        model_override = ctx.payload.get("model")
        service = SpeechToTextService(model=model_override)
        audio_path = ctx.get("audio_path") or (self.source_path(ctx) if service.requires_audio else None)
        duration = ctx.get("duration")

        started = time.perf_counter()
        try:
            result = service.transcribe(
                audio_path, language=ctx.get("language_hint"), duration=duration,
                task=ctx.payload.get("transcript_task", "transcribe"),
            )
        except ProcessingError as exc:
            _raise_stage(exc)
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        ctx.set("stt_result", result)
        ctx.set("processing_ms", elapsed_ms)
        return StageResult(
            message=f"{len(result.segments)} segments via {result.provider}/{result.model} "
                    f"({result.language})",
            data={"segments": len(result.segments), "language": result.language},
        )


@register_stage
class TranscriptCleanupStage(MeetingStage):
    key = "transcript_cleanup"
    name = "Transcript Cleanup"

    def run(self, ctx) -> StageResult:
        result = ctx.get("stt_result")
        cleanup = TranscriptCleanupService()
        clean_text = cleanup.clean_full([s.text for s in result.segments])
        raw_text = " ".join(s.text.strip() for s in result.segments).strip()
        ctx.set("clean_text", clean_text)
        ctx.set("raw_text", raw_text)
        return StageResult(message=f"{len(clean_text)} chars cleaned")


@register_stage
class TranscriptSegmentationStage(MeetingStage):
    key = "transcript_segmentation"
    name = "Transcript Segmentation"

    def run(self, ctx) -> StageResult:
        result = ctx.get("stt_result")
        rows = TranscriptSegmentationService().build(result)
        ctx.set("segment_rows", rows)
        return StageResult(message=f"{len(rows)} segments prepared")


@register_stage
class SpeakerDiarizationStage(MeetingStage):
    """Assign a speaker to each segment (Phase 15). Off by default; skips
    gracefully when disabled or the provider/audio is unavailable → one speaker."""

    key = "speaker_diarization"
    name = "Speaker Diarization"
    retryable = False

    def run(self, ctx) -> StageResult:
        from apps.meetings.services.diarization import (
            DiarizationError, diarization_enabled, get_diarization_provider,
        )

        if not diarization_enabled():
            return StageResult(skipped=True, message="diarization disabled")
        rows = ctx.get("segment_rows") or []
        if not rows:
            return StageResult(skipped=True, message="no segments")

        provider = get_diarization_provider()
        audio_path = ctx.get("audio_path")
        # Audio-based providers need the normalized wav; the dummy provider doesn't.
        if provider.name != "dummy" and (not audio_path or not os.path.exists(audio_path)):
            return StageResult(skipped=True, message="no audio available for diarization")

        segments = [(r["start_time"], r["end_time"]) for r in rows]
        try:
            diar = provider.diarize(audio_path or "", segments=segments, duration=ctx.get("duration"))
        except DiarizationError as exc:
            logger.warning("Diarization skipped: %s", exc)
            return StageResult(skipped=True, message=f"diarization unavailable: {exc}")

        ctx.set("diarization", diar)
        return StageResult(
            message=f"{diar.num_speakers} speaker(s) via {diar.provider}",
            data={"speakers": diar.num_speakers, "provider": diar.provider},
        )


# Distinct, color-blind-friendly palette for speaker chips.
_SPEAKER_COLORS = [
    "#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed",
    "#0891b2", "#db2777", "#65a30d", "#ea580c", "#4f46e5",
]


@register_stage
class StoreTranscriptStage(MeetingStage):
    key = "store_transcript"
    name = "Store Transcript"
    retryable = False

    def run(self, ctx) -> StageResult:
        from django.db import transaction

        from apps.meetings.models import Speaker, Transcript, TranscriptSegment

        meeting = self.meeting(ctx)
        cf = self.current_file(ctx)
        result = ctx.get("stt_result")
        rows = ctx.get("segment_rows") or []
        diar = ctx.get("diarization")  # DiarizationResult or None

        confidences = [r["confidence"] for r in rows if r["confidence"] is not None]
        avg_conf = round(sum(confidences) / len(confidences), 4) if confidences else None
        clean_text = ctx.get("clean_text", "")
        word_count = sum(r["word_count"] for r in rows)

        with transaction.atomic():
            # Idempotent / retranscribe-safe: hard-replace prior transcript +
            # segments + speakers (version history lives on MeetingFile, not here).
            # A plain .delete() would soft-delete and collide on unique constraints.
            TranscriptSegment.all_objects.filter(meeting=meeting).hard_delete()
            Transcript.all_objects.filter(meeting=meeting).hard_delete()
            Speaker.all_objects.filter(meeting=meeting).hard_delete()

            transcript = Transcript.objects.create(
                meeting=meeting,
                file=cf,
                raw_text=ctx.get("raw_text", ""),
                clean_text=clean_text,
                word_count=word_count,
                char_count=len(clean_text),
                detected_language=result.language,
                language_confidence=result.language_confidence,
                avg_confidence=avg_conf,
                model_used=result.model,
                provider=result.provider,
                processing_ms=ctx.get("processing_ms"),
                audio_duration_seconds=result.duration or ctx.get("duration"),
            )

            # Speaker entities (Phase 15). One Speaker per diarization cluster;
            # embeddings are persisted now for future cross-meeting recognition.
            speaker_by_label: dict[str, Speaker] = {}
            if diar and diar.segment_labels:
                distinct = []
                for lbl in diar.segment_labels:
                    if lbl and lbl not in distinct:
                        distinct.append(lbl)
                for n, lbl in enumerate(distinct, start=1):
                    speaker_by_label[lbl] = Speaker.objects.create(
                        meeting=meeting, label=f"Speaker {n}", diarization_label=lbl,
                        color=_SPEAKER_COLORS[(n - 1) % len(_SPEAKER_COLORS)],
                        embedding=diar.embeddings.get(lbl),
                    )

            def _speaker_for(i: int):
                if diar and i < len(diar.segment_labels):
                    return speaker_by_label.get(diar.segment_labels[i])
                return None

            TranscriptSegment.objects.bulk_create([
                TranscriptSegment(
                    meeting=meeting, index=r["index"], start_time=r["start_time"],
                    end_time=r["end_time"],
                    speaker=(sp.label if (sp := _speaker_for(i)) else r["speaker"]),
                    speaker_ref=_speaker_for(i), text=r["text"],
                    confidence=r["confidence"], word_count=r["word_count"],
                ) for i, r in enumerate(rows)
            ])

            # Per-speaker analytics (talk time / segments / words / avg confidence).
            for lbl, sp in speaker_by_label.items():
                idx = [i for i, l in enumerate(diar.segment_labels) if l == lbl]
                talk = sum(rows[i]["end_time"] - rows[i]["start_time"] for i in idx)
                words = sum(rows[i]["word_count"] for i in idx)
                confs = [rows[i]["confidence"] for i in idx if rows[i]["confidence"] is not None]
                sp.talk_time_seconds = round(talk, 2)
                sp.segment_count = len(idx)
                sp.word_count = words
                sp.avg_confidence = round(sum(confs) / len(confs), 4) if confs else None
                sp.save(update_fields=[
                    "talk_time_seconds", "segment_count", "word_count", "avg_confidence", "updated_at",
                ])

            # Multiple embeddings + quality signals (Phase 15) — persisted now so
            # 15B VoicePerson matching needs no reprocessing. Best-effort: a failure
            # here must not lose a good transcript.
            if speaker_by_label:
                try:
                    from apps.meetings.services.speaker_quality import persist_speaker_signals

                    persist_speaker_signals(meeting, speaker_by_label, diar, rows)
                except Exception:  # noqa: BLE001
                    logger.warning("Speaker quality signals skipped", exc_info=True)

        # Reflect detected language on the meeting if the user left the default.
        if meeting.language == "en" and result.language and result.language != "en":
            meeting.language = result.language
            meeting.save(update_fields=["language", "updated_at"])

        ctx.set("transcript_id", str(transcript.id))
        return StageResult(message=f"stored transcript ({word_count} words)",
                           data={"transcript_id": str(transcript.id)})


@register_stage
class SpeakerNamingStage(MeetingStage):
    """AI SUGGESTS speaker names from the transcript (Phase 15) — never auto-applies.
    Best-effort; gated on diarization being enabled with at least one speaker."""

    key = "speaker_naming"
    name = "Speaker Naming (AI suggestions)"
    retryable = False

    def run(self, ctx) -> StageResult:
        from apps.meetings.models import Speaker
        from apps.meetings.services.diarization import diarization_enabled
        from apps.meetings.services.speaker_naming import suggest_speaker_names

        if not diarization_enabled():
            return StageResult(skipped=True, message="diarization disabled")
        meeting = self.meeting(ctx)
        if not Speaker.objects.filter(meeting=meeting).exists():
            return StageResult(skipped=True, message="no speakers to name")
        try:
            n = suggest_speaker_names(meeting)
        except Exception:  # noqa: BLE001 — suggestions are best-effort
            logger.debug("Speaker naming failed", exc_info=True)
            return StageResult(skipped=True, message="naming unavailable")
        return StageResult(message=f"{n} AI name suggestion(s)", data={"suggestions": n})


class TranscriptStage(MeetingStage):
    """Base for AI stages: resolves the current transcript from the DB (so the AI
    stages work in both the combined pipeline and the standalone regenerate one)."""

    def transcript(self, ctx):
        t = ctx.get("transcript_obj")
        if t is None:
            from apps.meetings.models import Transcript

            t = Transcript.objects.filter(meeting=self.meeting(ctx)).order_by("-created_at").first()
            ctx.set("transcript_obj", t)
        return t


@register_stage
class TranslationStage(TranscriptStage):
    """Translate the transcript into a target language (Phase 13).

    The ORIGINAL transcript/segments are never overwritten — the translation is
    stored in separate fields so the UI can switch instantly. Skipped when the
    transcript language is "original". Reuses the config-selected TranslationProvider.
    """

    key = "translation"
    name = "Translation"

    def run(self, ctx) -> StageResult:
        from django.db import transaction

        from apps.meetings.models import TranscriptSegment
        from apps.meetings.services.translation import get_translation_provider

        meeting = self.meeting(ctx)
        target = ctx.payload.get("target_language") or (meeting.transcript_language if meeting else "")
        if not target or target in ("original", "source"):
            return StageResult(skipped=True, message="original transcript kept")

        transcript = self.transcript(ctx)
        segments = list(TranscriptSegment.objects.filter(meeting=meeting).order_by("index"))
        if transcript is None or not segments:
            return StageResult(skipped=True, message="no transcript to translate")
        # Already in the target language → nothing to do.
        if transcript.detected_language and transcript.detected_language == target:
            return StageResult(skipped=True, message=f"transcript already in {target}")

        provider = get_translation_provider()
        try:
            result = provider.translate(
                [s.text for s in segments], target_language=target,
                source_language=transcript.detected_language or None,
            )
        except Exception as exc:  # noqa: BLE001 — translation is best-effort, never fails the run
            return StageResult(skipped=True, message=f"translation unavailable ({type(exc).__name__})")

        with transaction.atomic():
            for seg, txt in zip(segments, result.segments):
                seg.translated_text = txt or ""
            TranscriptSegment.objects.bulk_update(segments, ["translated_text"])
            transcript.translated_text = result.text
            transcript.target_language = target
            transcript.translation_provider = result.provider
            transcript.translation_confidence = result.confidence
            transcript.translation_ms = result.ms
            transcript.save(update_fields=[
                "translated_text", "target_language", "translation_provider",
                "translation_confidence", "translation_ms", "updated_at",
            ])
        return StageResult(
            message=f"translated {len(segments)} segments → {target} via {result.provider}",
            data={"target": target, "provider": result.provider},
        )


@register_stage
class AIAnalysisStage(TranscriptStage):
    """Single structured LLM inference producing ALL artifacts (Phase 7)."""

    key = "ai_analysis"
    name = "AI Analysis"

    def run(self, ctx) -> StageResult:
        from apps.meetings.services.ai import AISummarizationService

        transcript = self.transcript(ctx)
        if transcript is None or not transcript.clean_text:
            raise NonRetryableStageError("No transcript is available to summarize.")
        meeting = self.meeting(ctx)
        output_language = ctx.payload.get("output_language") or (meeting.ai_language if meeting else "")
        ctx.set("output_language", output_language)
        service = AISummarizationService(model=ctx.payload.get("ai_model"))
        fallback = False
        # When speakers are known, feed the LLM a speaker-labeled transcript so it
        # attributes action-item owners / who made each decision / who raised each
        # risk (Phase 15) — this ownership flows into Workspace/Knowledge/Executive.
        analysis_text = self._attributed_text(meeting) or transcript.clean_text
        try:
            result = service.analyze(analysis_text, output_language=output_language)
        except ProcessingError as exc:
            # If the local model simply can't produce a valid summary for this
            # transcript (e.g. hard/long non-English content), DON'T discard a good
            # transcript — complete the meeting with a deterministic fallback summary.
            # Transient failures (llm_error, empty_transcript) still fail/retry.
            if exc.code == "ai_invalid_json":
                logger.warning("AI summary unavailable for meeting %s (%s); completing with a "
                               "fallback summary so the transcript isn't lost.",
                               getattr(meeting, "id", None), exc)
                result = service.fallback(transcript.clean_text)
                fallback = True
            else:
                _raise_stage(exc)
        ctx.set("ai_result", result)
        p = result.parsed
        suffix = " (fallback — model could not summarize)" if fallback else ""
        return StageResult(
            message=(f"{result.provider}/{result.model}: summary + "
                     f"{len(p['action_items'])} actions, {len(p['decisions'])} decisions "
                     f"({result.chunks} chunk(s)){suffix}"),
            data={"chunks": result.chunks, "provider": result.provider, "fallback": fallback},
        )

    @staticmethod
    def _attributed_text(meeting) -> str:
        """A speaker-labeled transcript for AI attribution, or "" if no speakers."""
        from apps.meetings.models import Speaker

        if not Speaker.objects.filter(meeting=meeting).exists():
            return ""
        from apps.meetings.services.speaker_naming import build_labeled_transcript

        return build_labeled_transcript(meeting, use_names=True, limit=100_000)


@register_stage
class StoreAIResultsStage(TranscriptStage):
    """Persist a NEW versioned AIAnalysis — never overwrites prior results."""

    key = "store_ai_results"
    name = "Store AI Results"
    retryable = False

    def run(self, ctx) -> StageResult:
        from django.conf import settings
        from django.db import transaction
        from django.db.models import Max

        from apps.meetings.models import AIAnalysis

        meeting = self.meeting(ctx)
        result = ctx.get("ai_result")
        p = result.parsed
        with transaction.atomic():
            next_version = (
                AIAnalysis.all_objects.filter(meeting=meeting).aggregate(m=Max("version"))["m"] or 0
            ) + 1
            AIAnalysis.objects.filter(meeting=meeting).update(is_current=False)
            analysis = AIAnalysis.objects.create(
                meeting=meeting, file=self.current_file(ctx), version=next_version, is_current=True,
                executive_summary=p["executive_summary"], detailed_summary=p["detailed_summary"],
                bullet_summary=p["bullet_summary"], meeting_minutes=p["meeting_minutes"],
                action_items=p["action_items"], decisions=p["decisions"], risks=p["risks"],
                issues=p.get("issues", []),
                follow_ups=p["follow_ups"], deadlines=p["deadlines"], keywords=p["keywords"],
                raw_response=result.raw_response, parsed_response=p,
                model_used=result.model, provider=result.provider,
                prompt_version=result.prompt_version, inference_ms=result.inference_ms,
                temperature=settings.AI_TEMPERATURE, chunks=result.chunks,
                output_language=ctx.get("output_language", ""),
            )
        ctx.set("analysis_id", str(analysis.id))
        return StageResult(message=f"stored AI analysis v{next_version}",
                           data={"analysis_id": str(analysis.id), "version": next_version})


@register_stage
class FinalizeStage(MeetingStage):
    key = "finalize"
    name = "Finalize"

    def run(self, ctx) -> StageResult:
        # Clean up any temp audio files; never touches the original upload.
        removed = 0
        for path in ctx.shared.get("temp_files", []):
            try:
                if path and os.path.exists(path):
                    os.remove(path)
                    removed += 1
            except OSError:
                logger.debug("Failed to remove temp file %s", path, exc_info=True)
        return StageResult(message=f"finalized (cleaned {removed} temp file(s))")


# Full meeting pipeline — transcription (Phase 6) + AI analysis (Phase 7).
# The AI analysis is a single structured LLM inference (all artifacts at once).
MEETING_PROCESSING = register_pipeline(PipelineDefinition(
    name="meeting_processing",
    description="Validate → inspect → extract → normalize → detect language → "
                "transcribe → clean → segment → store transcript → AI analysis → "
                "store AI → finalize",
    stages=[
        "validation", "media_inspection", "audio_extraction", "audio_normalization",
        "language_detection", "speech_to_text", "transcript_cleanup",
        "transcript_segmentation", "speaker_diarization", "store_transcript",
        "speaker_naming", "translation", "ai_analysis", "store_ai_results", "finalize",
    ],
    dependencies={
        "media_inspection": ["validation"],
        "audio_extraction": ["media_inspection"],
        "audio_normalization": ["audio_extraction"],
        "language_detection": ["audio_normalization"],
        "speech_to_text": ["language_detection"],
        "transcript_cleanup": ["speech_to_text"],
        "transcript_segmentation": ["transcript_cleanup"],
        "speaker_diarization": ["transcript_segmentation"],
        "store_transcript": ["speaker_diarization"],
        "speaker_naming": ["store_transcript"],
        "translation": ["speaker_naming"],
        "ai_analysis": ["translation"],
        "store_ai_results": ["ai_analysis"],
        "finalize": ["store_ai_results"],
    },
))

# Standalone AI pipeline for "regenerate summary" — reuses the existing transcript.
AI_SUMMARIZATION = register_pipeline(PipelineDefinition(
    name="ai_summarization",
    description="AI analysis → store AI → finalize (reuses the stored transcript)",
    stages=["ai_analysis", "store_ai_results", "finalize"],
    dependencies={
        "store_ai_results": ["ai_analysis"],
        "finalize": ["store_ai_results"],
    },
))
