"""Cross-meeting voice identity (Phase 15B).

Links per-meeting ``Speaker`` rows to org-wide ``VoicePerson`` identities via
similarity search over the voice embeddings already persisted at processing time
(Phase 15) — so NO transcript/embedding reprocessing is ever needed. Matching is
suggestion-only and TIERED to limit false positives; a human always confirms.

Pure-Python vector math (no torch/numpy) so it runs anywhere the pipeline does.
Everything is owner-scoped; a VoicePerson only ever sees its owner's speakers.
"""
from __future__ import annotations

import math

from django.conf import settings
from django.utils import timezone

from apps.meetings.enums import SpeakerEmbeddingKind
from apps.meetings.models import Speaker, SpeakerEmbedding

from ..enums import VoiceMatchTier, VoicePersonEventType
from ..models import VoicePerson, VoicePersonEvent

__all__ = [
    "find_candidates", "suggest_for_meeting", "create_from_speaker", "link_speaker",
    "unlink_speaker", "confirm", "update_identity", "merge", "split", "recompute", "tier_for",
]


# --- vector helpers ---------------------------------------------------------
def _norm(v) -> float:
    return math.sqrt(sum(x * x for x in v)) or 1e-9


def _cosine(a, b) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (_norm(a) * _norm(b))


def _centroid(vectors) -> list[float]:
    vectors = [v for v in vectors if v]
    if not vectors:
        return []
    dims = len(vectors[0])
    mean = [sum(v[i] for v in vectors) / len(vectors) for i in range(dims)]
    n = _norm(mean)
    return [x / n for x in mean]


def speaker_centroid(speaker: Speaker) -> list[float]:
    """The speaker's voice signature: the persisted centroid embedding (or the
    legacy single embedding), used for similarity search."""
    row = (
        SpeakerEmbedding.objects.filter(speaker=speaker, kind=SpeakerEmbeddingKind.CENTROID)
        .first()
    )
    if row and row.vector:
        return row.vector
    return speaker.embedding or []


# --- confidence tiers -------------------------------------------------------
def tier_for(score: float) -> str:
    if score >= float(getattr(settings, "VOICE_MATCH_AUTO_HIGHLIGHT", 98.0)):
        return VoiceMatchTier.AUTO_HIGHLIGHT
    if score >= float(getattr(settings, "VOICE_MATCH_HIGHLY_LIKELY", 95.0)):
        return VoiceMatchTier.HIGHLY_LIKELY
    if score >= float(getattr(settings, "VOICE_MATCH_POSSIBLE", 90.0)):
        return VoiceMatchTier.POSSIBLE
    return VoiceMatchTier.NONE


def _score(speaker_vec, person: VoicePerson) -> float:
    """Best cosine agreement (0-100) between a speaker centroid and an identity —
    max of centroid-to-centroid and centroid-to-best-embedding (robust to a
    speaker whose single meeting only captured part of the voice)."""
    if not speaker_vec:
        return 0.0
    best = _cosine(speaker_vec, person.voice_centroid_embedding or [])
    for be in (person.best_embeddings or []):
        best = max(best, _cosine(speaker_vec, be.get("vector") or []))
    return round(100.0 * max(0.0, best), 2)


# --- matching ---------------------------------------------------------------
def find_candidates(speaker: Speaker, *, top_n: int | None = None) -> list[dict]:
    """Ranked identity candidates for a meeting speaker (suggestion-only).

    Returns [{voice_person, score, tier}] above the suggestion floor, best first.
    Never links anything. Owner-scoped to the speaker's meeting owner.
    """
    top_n = top_n or int(getattr(settings, "VOICE_MATCH_TOP_N", 5))
    vec = speaker_centroid(speaker)
    if not vec:
        return []
    owner_id = speaker.meeting.owner_id
    candidates = []
    for person in VoicePerson.objects.filter(owner_id=owner_id):
        score = _score(vec, person)
        tier = tier_for(score)
        if tier == VoiceMatchTier.NONE:
            continue
        candidates.append({"voice_person": person, "score": score, "tier": tier})
    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[:top_n]


def suggest_for_meeting(meeting) -> list[dict]:
    """Per-speaker identity suggestions for a meeting's UNLINKED speakers."""
    out = []
    for sp in Speaker.objects.filter(meeting=meeting, voice_person__isnull=True):
        out.append({"speaker": sp, "candidates": find_candidates(sp)})
    return out


# --- aggregation ------------------------------------------------------------
def recompute(person: VoicePerson) -> VoicePerson:
    """Rebuild a VoicePerson's signature + analytics from its linked speakers.
    Uses only already-persisted embeddings — no reprocessing."""
    speakers = list(Speaker.objects.filter(voice_person=person).select_related("meeting"))
    centroids = [speaker_centroid(sp) for sp in speakers]
    person.voice_centroid_embedding = _centroid(centroids)
    person.embedding_dimensions = len(person.voice_centroid_embedding)

    # Best-N representative embeddings across all linked speakers.
    best_rows = list(
        SpeakerEmbedding.objects.filter(
            speaker__voice_person=person, kind=SpeakerEmbeddingKind.BEST_N
        ).order_by("-quality")[: int(getattr(settings, "VOICE_PERSON_BEST_N", 5))]
    )
    person.best_embeddings = [
        {
            "vector": r.vector, "quality": r.quality,
            "meeting_id": str(r.speaker.meeting_id), "speaker_id": str(r.speaker_id),
        }
        for r in best_rows
    ]

    person.speaker_count = len(speakers)
    person.meeting_count = len({sp.meeting_id for sp in speakers})
    person.total_talk_time = round(sum(sp.talk_time_seconds for sp in speakers), 2)
    person.total_word_count = sum(sp.word_count for sp in speakers)
    quals = [sp.avg_confidence for sp in speakers if sp.avg_confidence is not None]
    person.avg_embedding_quality = round(sum(quals) / len(quals), 4) if quals else None
    seens = [sp.meeting.created_at for sp in speakers if sp.meeting]
    person.last_seen = max(seens) if seens else None
    person.save()
    return person


def _event(person, event_type, *, actor=None, speaker=None, confidence=None, tier="", detail=None):
    VoicePersonEvent.objects.create(
        owner=person.owner, voice_person=person, event_type=event_type, actor=actor,
        speaker_id=getattr(speaker, "id", None),
        meeting_id=getattr(speaker, "meeting_id", None) if speaker else None,
        confidence=confidence, tier=tier or "", detail=detail or {},
    )


# --- lifecycle --------------------------------------------------------------
def create_from_speaker(speaker: Speaker, *, display_name: str = "", workspace=None,
                        actor=None) -> VoicePerson:
    """Create a brand-new identity seeded from a meeting speaker + link it."""
    owner = speaker.meeting.owner
    person = VoicePerson.objects.create(
        owner=owner, workspace=workspace,
        display_name=display_name or speaker.name or speaker.label,
        confirmed=bool(actor),
    )
    _event(person, VoicePersonEventType.CREATED, actor=actor)
    link_speaker(person, speaker, actor=actor, confidence=100.0, log=True)
    return person


def link_speaker(person: VoicePerson, speaker: Speaker, *, actor=None,
                 confidence: float | None = None, tier: str = "", log: bool = True) -> VoicePerson:
    """Link a meeting speaker to an identity (user-confirmed). Recomputes the
    identity's signature + analytics. Owner-scoped: the speaker's owner must match."""
    if speaker.meeting.owner_id != person.owner_id:
        raise PermissionError("Speaker and VoicePerson have different owners.")
    speaker.voice_person = person
    if confidence is not None:
        speaker.recognition_confidence = confidence
    speaker.save(update_fields=["voice_person", "recognition_confidence", "updated_at"])
    if confidence is not None:
        person.confidence = confidence
    recompute(person)
    if log:
        _event(person, VoicePersonEventType.LINKED, actor=actor, speaker=speaker,
               confidence=confidence, tier=tier)
    return person


def unlink_speaker(speaker: Speaker, *, actor=None) -> VoicePerson | None:
    """Detach a speaker from its identity and recompute that identity."""
    person = speaker.voice_person
    if person is None:
        return None
    speaker.voice_person = None
    speaker.recognition_confidence = None
    speaker.save(update_fields=["voice_person", "recognition_confidence", "updated_at"])
    recompute(person)
    _event(person, VoicePersonEventType.UNLINKED, actor=actor, speaker=speaker)
    return person


def confirm(person: VoicePerson, *, actor=None) -> VoicePerson:
    person.confirmed = True
    person.save(update_fields=["confirmed", "updated_at"])
    _event(person, VoicePersonEventType.CONFIRMED, actor=actor)
    return person


_EDITABLE = {"display_name", "aliases", "avatar", "email", "department", "role"}


def update_identity(person: VoicePerson, changes: dict, *, actor=None) -> VoicePerson:
    fields = []
    renamed = "display_name" in changes and changes["display_name"] != person.display_name
    for k, v in changes.items():
        if k in _EDITABLE:
            setattr(person, k, v)
            fields.append(k)
    if fields:
        person.save(update_fields=[*fields, "updated_at"])
        _event(person, VoicePersonEventType.RENAMED if renamed else VoicePersonEventType.EDITED,
               actor=actor, detail={"fields": fields})
    return person


def merge(target: VoicePerson, source: VoicePerson, *, actor=None) -> VoicePerson:
    """Fold ``source`` into ``target``: relink all of source's speakers, merge
    aliases, recompute, and archive source. History is preserved via events."""
    if target.owner_id != source.owner_id:
        raise PermissionError("Cannot merge identities across owners.")
    if target.id == source.id:
        return target
    Speaker.objects.filter(voice_person=source).update(voice_person=target)
    merged_aliases = list(dict.fromkeys([*target.aliases, source.display_name, *source.aliases]))
    target.aliases = [a for a in merged_aliases if a and a != target.display_name]
    target.save(update_fields=["aliases", "updated_at"])
    recompute(target)
    _event(target, VoicePersonEventType.MERGED, actor=actor,
           detail={"merged_from": str(source.id), "merged_name": source.display_name})
    source.delete()  # soft-delete; its events remain for audit
    return target


def split(person: VoicePerson, speaker_ids: list, *, new_name: str = "", actor=None) -> VoicePerson:
    """Split the given speakers out of ``person`` into a NEW identity."""
    speakers = list(Speaker.objects.filter(voice_person=person, id__in=speaker_ids))
    if not speakers:
        raise ValueError("No matching linked speakers to split.")
    new_person = VoicePerson.objects.create(
        owner=person.owner, workspace=person.workspace,
        display_name=new_name or f"{person.display_name} (split)", confirmed=bool(actor),
    )
    _event(new_person, VoicePersonEventType.CREATED, actor=actor,
           detail={"split_from": str(person.id)})
    Speaker.objects.filter(id__in=[s.id for s in speakers]).update(voice_person=new_person)
    recompute(new_person)
    recompute(person)
    _event(person, VoicePersonEventType.SPLIT, actor=actor,
           detail={"split_to": str(new_person.id), "speakers": [str(s.id) for s in speakers]})
    return new_person
