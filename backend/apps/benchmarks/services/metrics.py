"""Diarization scoring metrics (req 3).

Two tiers, matching the honesty requirement (req 8):

* COUNT-BASED (approximate) — from expected vs detected speaker COUNT only. This
  is all that public recordings support unless a human labelled them. It cannot
  tell *which* speakers were confused, only that counts differ.
* SEGMENT-LEVEL (high-confidence) — when a recording carries per-segment reference
  labels (RTTM-style), detected clusters are time-aligned to reference speakers to
  compute cluster purity, a confusion-based DER approximation, and real
  over-merge / over-split counts.

The caller picks the tier via ``evaluate`` (segment-level when reference present).
Pure Python — no numpy/sklearn — so it runs anywhere the dummy provider does.
"""
from __future__ import annotations

from collections import defaultdict


def count_metrics(expected: int | None, detected: int) -> dict:
    """Count-level proxy metrics. Honest: these estimate from counts alone."""
    if expected is None:
        return {
            "correctly_clustered": None,
            "over_merged": 0,
            "over_split": 0,
        }
    return {
        "correctly_clustered": min(expected, detected),
        "over_merged": max(0, expected - detected),   # fewer detected → voices merged
        "over_split": max(0, detected - expected),    # more detected → a voice split
    }


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def segment_metrics(
    detected: list[tuple[float, float, str]],
    reference: list[tuple[float, float, str]],
) -> dict:
    """Time-aligned metrics from per-segment detected vs reference labels.

    ``detected``/``reference`` are lists of (start, end, speaker_label).
    """
    ref_total = sum(e - s for s, e, _ in reference) or 1e-9

    # For each detected cluster, how much time it overlaps each reference speaker.
    det_to_ref = defaultdict(lambda: defaultdict(float))
    for ds, de, dlabel in detected:
        for rs, re_, rlabel in reference:
            ov = _overlap(ds, de, rs, re_)
            if ov > 0:
                det_to_ref[dlabel][rlabel] += ov

    # Purity: each detected cluster is "worth" its single best reference match.
    correct_time = 0.0
    det_dominant: dict[str, str] = {}
    det_time_total = 0.0
    for dlabel, ref_overlaps in det_to_ref.items():
        best_ref = max(ref_overlaps, key=ref_overlaps.get)
        det_dominant[dlabel] = best_ref
        correct_time += ref_overlaps[best_ref]
        det_time_total += sum(ref_overlaps.values())
    det_time_total = det_time_total or 1e-9

    cluster_purity = round(correct_time / det_time_total, 4)
    der = round(max(0.0, 1.0 - correct_time / ref_total), 4)  # confusion-based approximation

    # Real over-merge / over-split from the dominant mapping.
    ref_speakers = {r for _, _, r in reference}
    covered_refs = set(det_dominant.values())
    # A reference speaker is "over-merged" if it never becomes any cluster's dominant.
    over_merged = len(ref_speakers - covered_refs)
    # Over-split: reference speakers claimed by more than one detected cluster.
    ref_claim_counts: dict[str, int] = defaultdict(int)
    for ref in det_dominant.values():
        ref_claim_counts[ref] += 1
    over_split = sum(c - 1 for c in ref_claim_counts.values() if c > 1)
    correctly_clustered = len(covered_refs) - over_split
    correctly_clustered = max(0, correctly_clustered)

    return {
        "correctly_clustered": correctly_clustered,
        "over_merged": over_merged,
        "over_split": over_split,
        "cluster_purity": cluster_purity,
        "der": der,
    }


def evaluate(
    expected: int | None,
    detected_count: int,
    *,
    detected: list[tuple[float, float, str]] | None = None,
    reference: list[tuple[float, float, str]] | None = None,
) -> dict:
    """Unified scoring: segment-level when a reference is supplied, else count-based.

    Always returns every req-3 clustering key; segment-only keys (der,
    cluster_purity) are None in the count-based case.
    """
    if reference and detected:
        m = segment_metrics(detected, reference)
        m["expected_speaker_count"] = expected if expected is not None else len({r for _, _, r in reference})
        m["detected_speaker_count"] = detected_count
        return m
    m = count_metrics(expected, detected_count)
    m["expected_speaker_count"] = expected
    m["detected_speaker_count"] = detected_count
    m["cluster_purity"] = None
    m["der"] = None
    return m
