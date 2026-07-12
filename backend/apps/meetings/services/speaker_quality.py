"""Speaker quality signals + multiple voice embeddings (Phase 15).

Generated at processing time from the diarization output so Phase 15B VoicePerson
recognition never needs to re-embed audio (requirement #5/#9). All acoustic-ish
signals derived here are geometric/confidence proxies — honestly flagged
``approximate=True`` — not measured from raw waveform SNR, so nothing downstream
overstates them (requirement #8).

The heavy diarization deps (torch/speechbrain) are NOT imported here: this module
works purely off the vectors already produced by the provider, using tiny
pure-Python vector math so it also runs under the dummy provider in tests.
"""
from __future__ import annotations

import math

from django.conf import settings

from apps.meetings.enums import SpeakerEmbeddingKind
from apps.meetings.models import SpeakerEmbedding, SpeakerQualitySignal

__all__ = ["persist_speaker_signals"]


def _norm(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v)) or 1e-9


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (_norm(a) * _norm(b))


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _segment_quality(sim_to_centroid: float, duration: float) -> float:
    """0-100 quality of one segment embedding: agreement with the speaker centroid
    weighted with duration adequacy (short clips embed less reliably)."""
    dur_factor = _clamp(duration / 3.0)  # ~3s is plenty for a stable ECAPA embedding
    return round(100.0 * (0.7 * _clamp(sim_to_centroid) + 0.3 * dur_factor), 2)


def _overlap_ratio(mine: list[tuple[float, float]], others: list[tuple[float, float]]) -> float:
    """Fraction of this speaker's speech time that overlaps another speaker's spans."""
    total = sum(e - s for s, e in mine) or 1e-9
    overlapped = 0.0
    for ms, me in mine:
        for os_, oe in others:
            overlapped += max(0.0, min(me, oe) - max(ms, os_))
    return _clamp(overlapped / total)


def _silence_ratio(mine: list[tuple[float, float]]) -> float:
    """Silence within the speaker's [first_start, last_end] envelope (approx)."""
    if not mine:
        return 0.0
    envelope = max(e for _, e in mine) - min(s for s, _ in mine)
    if envelope <= 0:
        return 0.0
    covered = sum(e - s for s, e in mine)
    return _clamp((envelope - covered) / envelope)


def persist_speaker_signals(meeting, speaker_by_label: dict, diar, rows: list[dict]) -> int:
    """Create SpeakerEmbedding rows (segment/centroid/best_n) + a SpeakerQualitySignal
    for every diarized speaker of ``meeting``. Returns the number of speakers scored.

    Must run inside the StoreTranscriptStage transaction, after speakers/segments
    exist. No-op (returns 0) when there is no usable diarization output.
    """
    if not diar or not getattr(diar, "segment_labels", None):
        return 0

    labels = diar.segment_labels
    seg_embs = getattr(diar, "segment_embeddings", None) or []
    store_segments = bool(getattr(settings, "SPEAKER_STORE_SEGMENT_EMBEDDINGS", True))
    best_n = int(getattr(settings, "SPEAKER_BEST_N", 3))
    min_dur = float(getattr(settings, "SPEAKER_MIN_EMBED_DURATION", 0.35))
    provider = getattr(diar, "provider", "")
    model = getattr(diar, "model", "")

    scored = 0
    for lbl, sp in speaker_by_label.items():
        idx = [i for i, l in enumerate(labels) if l == lbl]
        if not idx:
            continue
        mine = [(rows[i]["start_time"], rows[i]["end_time"]) for i in idx]
        others = [
            (rows[i]["start_time"], rows[i]["end_time"])
            for i in range(len(rows))
            if i < len(labels) and labels[i] and labels[i] != lbl
        ]
        centroid = diar.embeddings.get(lbl) or sp.embedding
        dims = len(centroid) if centroid else 0

        # --- per-segment embeddings + their quality ---------------------
        per_segment: list[dict] = []
        for i in idx:
            vec = seg_embs[i] if i < len(seg_embs) else None
            if not vec:
                continue
            dur = rows[i]["end_time"] - rows[i]["start_time"]
            sim = _cosine(vec, centroid) if centroid else 0.0
            per_segment.append({
                "segment_index": rows[i]["index"],
                "vector": vec,
                "start_time": rows[i]["start_time"],
                "end_time": rows[i]["end_time"],
                "duration": round(dur, 3),
                "quality": _segment_quality(sim, dur),
                "sim": sim,
            })

        embedding_rows: list[SpeakerEmbedding] = []
        if centroid:
            embedding_rows.append(SpeakerEmbedding(
                speaker=sp, kind=SpeakerEmbeddingKind.CENTROID, vector=centroid,
                dimensions=dims, duration=round(sum(e - s for s, e in mine), 3),
                quality=round(sum(p["quality"] for p in per_segment) / len(per_segment), 2)
                if per_segment else None,
                provider=provider, model=model,
            ))
        if store_segments:
            for p in per_segment:
                embedding_rows.append(SpeakerEmbedding(
                    speaker=sp, kind=SpeakerEmbeddingKind.SEGMENT, vector=p["vector"],
                    dimensions=len(p["vector"]), segment_index=p["segment_index"],
                    start_time=p["start_time"], end_time=p["end_time"],
                    duration=p["duration"], quality=p["quality"],
                    provider=provider, model=model,
                ))
        # Best-N representatives: highest quality first.
        for rank, p in enumerate(
            sorted(per_segment, key=lambda x: x["quality"], reverse=True)[:best_n], start=1
        ):
            embedding_rows.append(SpeakerEmbedding(
                speaker=sp, kind=SpeakerEmbeddingKind.BEST_N, vector=p["vector"],
                dimensions=len(p["vector"]), segment_index=p["segment_index"],
                start_time=p["start_time"], end_time=p["end_time"],
                duration=p["duration"], quality=p["quality"], rank=rank,
                provider=provider, model=model,
            ))
        if embedding_rows:
            SpeakerEmbedding.objects.bulk_create(embedding_rows)

        # --- quality signals --------------------------------------------
        speech_duration = round(sum(e - s for s, e in mine), 3)
        confs = [rows[i]["confidence"] for i in idx if rows[i]["confidence"] is not None]
        avg_conf = round(sum(confs) / len(confs), 4) if confs else None
        usable = sum(1 for i in idx if (rows[i]["end_time"] - rows[i]["start_time"]) >= min_dur)
        emb_quality = (
            round(100.0 * _clamp(sum(p["sim"] for p in per_segment) / len(per_segment)), 2)
            if per_segment else None
        )
        overlap = round(_overlap_ratio(mine, others), 4)
        silence = round(_silence_ratio(mine), 4)
        noise = round(_clamp(1.0 - avg_conf), 4) if avg_conf is not None else None

        # Composite 0-100: embedding consistency, duration adequacy, confidence,
        # and a penalty for heavy overlap. Deterministic, no LLM.
        components: list[tuple[float, float]] = []  # (value, weight)
        if emb_quality is not None:
            components.append((emb_quality, 0.45))
        components.append((100.0 * _clamp(speech_duration / 30.0), 0.20))
        if avg_conf is not None:
            components.append((100.0 * _clamp(avg_conf), 0.20))
        components.append((100.0 * (1.0 - overlap), 0.15))
        total_weight = sum(w for _, w in components)
        signal_quality = round(sum(v * w for v, w in components) / total_weight, 2)

        SpeakerQualitySignal.objects.create(
            speaker=sp,
            signal_quality=signal_quality,
            noise_score=noise,
            speech_duration=speech_duration,
            avg_confidence=avg_conf,
            overlap_ratio=overlap,
            silence_ratio=silence,
            embedding_quality_score=emb_quality,
            usable_segments=usable,
            total_segments=len(idx),
            approximate=True,  # geometric/confidence proxies, not raw-acoustic SNR
        )
        scored += 1
    return scored
