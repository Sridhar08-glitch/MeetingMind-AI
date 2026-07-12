"""Unit tests for the diarization scoring metrics (pure, no DB)."""
from __future__ import annotations

from apps.benchmarks.services import metrics


def test_count_metrics_exact_match():
    m = metrics.count_metrics(3, 3)
    assert m == {"correctly_clustered": 3, "over_merged": 0, "over_split": 0}


def test_count_metrics_over_merged():
    # Expected 4 speakers, only 2 detected → 2 voices merged.
    m = metrics.count_metrics(4, 2)
    assert m["over_merged"] == 2
    assert m["over_split"] == 0
    assert m["correctly_clustered"] == 2


def test_count_metrics_over_split():
    # Expected 2 speakers, 5 detected → 3 over-splits.
    m = metrics.count_metrics(2, 5)
    assert m["over_split"] == 3
    assert m["over_merged"] == 0


def test_count_metrics_unknown_expected():
    m = metrics.count_metrics(None, 3)
    assert m["correctly_clustered"] is None


def test_segment_metrics_perfect_alignment():
    # Two speakers, detected clusters align 1:1 with reference speakers.
    ref = [(0.0, 5.0, "A"), (5.0, 10.0, "B")]
    det = [(0.0, 5.0, "SPEAKER_00"), (5.0, 10.0, "SPEAKER_01")]
    m = metrics.segment_metrics(det, ref)
    assert m["cluster_purity"] == 1.0
    assert m["der"] == 0.0
    assert m["over_merged"] == 0
    assert m["over_split"] == 0
    assert m["correctly_clustered"] == 2


def test_segment_metrics_over_merged():
    # Everything lumped into one detected cluster → one reference speaker uncovered.
    ref = [(0.0, 5.0, "A"), (5.0, 10.0, "B")]
    det = [(0.0, 5.0, "SPEAKER_00"), (5.0, 10.0, "SPEAKER_00")]
    m = metrics.segment_metrics(det, ref)
    assert m["over_merged"] == 1  # B never dominates a cluster
    assert m["der"] > 0.0


def test_segment_metrics_over_split():
    # One reference speaker split into two detected clusters.
    ref = [(0.0, 10.0, "A")]
    det = [(0.0, 5.0, "SPEAKER_00"), (5.0, 10.0, "SPEAKER_01")]
    m = metrics.segment_metrics(det, ref)
    assert m["over_split"] == 1
    # Purity is still perfect (both clusters are pure A); only the count split.
    assert m["cluster_purity"] == 1.0


def test_evaluate_prefers_segment_level_when_reference_present():
    ref = [(0.0, 5.0, "A"), (5.0, 10.0, "B")]
    det = [(0.0, 5.0, "SPEAKER_00"), (5.0, 10.0, "SPEAKER_01")]
    m = metrics.evaluate(2, 2, detected=det, reference=ref)
    assert m["cluster_purity"] == 1.0
    assert m["der"] == 0.0


def test_evaluate_falls_back_to_count_based():
    m = metrics.evaluate(3, 2)
    assert m["over_merged"] == 1
    assert m["cluster_purity"] is None
    assert m["der"] is None
