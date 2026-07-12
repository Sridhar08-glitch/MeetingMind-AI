"""Settings-free clustering for the tuning harness (req 6).

The harness re-clusters the segment embeddings that were persisted at processing
time (Phase 15 SpeakerEmbedding rows), so sweeping thresholds NEVER re-runs
Whisper or the ECAPA encoder — only the (cheap) clustering step. Every knob is an
explicit argument, so parallel/streaming sweeps never mutate global settings.

Uses scikit-learn when available; a pure-Python average-linkage fallback keeps the
module (and the tests, on the 16-dim dummy vectors) working with no heavy deps.
"""
from __future__ import annotations

import math


def _norm(v) -> float:
    return math.sqrt(sum(x * x for x in v)) or 1e-9


def cosine_sim(a, b) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (_norm(a) * _norm(b))


def centroid(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    dims = len(vectors[0])
    mean = [sum(v[i] for v in vectors) / len(vectors) for i in range(dims)]
    n = _norm(mean)
    return [x / n for x in mean]


def centroids_by_label(vectors, labels) -> dict:
    groups: dict[str, list] = {}
    for v, lbl in zip(vectors, labels):
        groups.setdefault(lbl, []).append(v)
    return {lbl: centroid(vs) for lbl, vs in groups.items()}


def _relabel(raw) -> list[str]:
    """Stable SPEAKER_NN labels in order of first appearance."""
    order: dict = {}
    out: list[str] = []
    for c in raw:
        if c not in order:
            order[c] = f"SPEAKER_{len(order):02d}"
        out.append(order[c])
    return out


def _agglomerative_py(vectors, threshold: float, max_speakers: int) -> list[int]:
    """Average-linkage cosine agglomerative clustering (small inputs / no sklearn)."""
    clusters = [[i] for i in range(len(vectors))]

    def link(ci, cj) -> float:
        dists = [1.0 - cosine_sim(vectors[a], vectors[b]) for a in ci for b in cj]
        return sum(dists) / len(dists)

    while len(clusters) > 1:
        best = None
        for a in range(len(clusters)):
            for b in range(a + 1, len(clusters)):
                d = link(clusters[a], clusters[b])
                if best is None or d < best[0]:
                    best = (d, a, b)
        d, a, b = best
        if len(clusters) <= max_speakers and d > threshold:
            break
        clusters[a].extend(clusters[b])
        del clusters[b]

    labels = [0] * len(vectors)
    for ci, members in enumerate(clusters):
        for i in members:
            labels[i] = ci
    return labels


def _merge_close(vectors, raw, merge_threshold: float):
    """Post-hoc merge of clusters whose centroids are within ``merge_threshold``
    cosine distance — mirrors the VoicePerson-style consolidation step."""
    labels = list(raw)
    while True:
        cents = centroids_by_label(vectors, labels)
        keys = list(cents)
        merged = False
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                if 1.0 - cosine_sim(cents[keys[i]], cents[keys[j]]) < merge_threshold:
                    labels = [keys[i] if l == keys[j] else l for l in labels]
                    merged = True
                    break
            if merged:
                break
        if not merged:
            return labels


def _mean_confidence(vectors, labels) -> float:
    """Mean cosine agreement of each vector with its cluster centroid → 0-100."""
    cents = centroids_by_label(vectors, labels)
    sims = [max(0.0, cosine_sim(v, cents[l])) for v, l in zip(vectors, labels)]
    return round(100.0 * (sum(sims) / len(sims)), 2) if sims else 0.0


def cluster_vectors(
    vectors: list[list[float]],
    *,
    threshold: float,
    max_speakers: int,
    merge_threshold: float | None = None,
) -> tuple[list[str], float]:
    """Cluster ``vectors`` → (per-vector SPEAKER_NN labels, embedding confidence 0-100)."""
    n = len(vectors)
    if n == 0:
        return [], 0.0
    if n == 1:
        return ["SPEAKER_00"], 100.0

    raw: list
    try:
        import numpy as np
        from sklearn.cluster import AgglomerativeClustering

        arr = np.array(vectors, dtype=float)
        model = AgglomerativeClustering(
            n_clusters=None, distance_threshold=threshold, metric="cosine", linkage="average"
        )
        raw = list(model.fit_predict(arr))
        if len(set(raw)) > max_speakers:
            raw = list(
                AgglomerativeClustering(
                    n_clusters=max_speakers, metric="cosine", linkage="average"
                ).fit_predict(arr)
            )
    except Exception:  # noqa: BLE001 — no sklearn/numpy: pure-Python fallback
        raw = _agglomerative_py(vectors, threshold, max_speakers)

    if merge_threshold is not None:
        raw = _merge_close(vectors, raw, merge_threshold)

    labels = _relabel(raw)
    return labels, _mean_confidence(vectors, labels)


def assign_nearest(vector, cents: dict) -> str:
    """Nearest-centroid label for a segment excluded from clustering (too short)."""
    if not cents:
        return "SPEAKER_00"
    return max(cents, key=lambda lbl: cosine_sim(vector, cents[lbl]))


def merge_small_speakers(vectors, labels, durations, min_speech_duration: float) -> list[str]:
    """Fold speakers whose total attributed speech is below ``min_speech_duration``
    into their nearest surviving speaker by centroid similarity."""
    if min_speech_duration <= 0:
        return labels
    totals: dict[str, float] = {}
    for lbl, dur in zip(labels, durations):
        totals[lbl] = totals.get(lbl, 0.0) + dur
    small = {lbl for lbl, t in totals.items() if t < min_speech_duration}
    survivors = [lbl for lbl in totals if lbl not in small]
    if not survivors or not small:
        return labels
    cents = centroids_by_label(vectors, labels)
    survivor_cents = {lbl: cents[lbl] for lbl in survivors}
    remap = {lbl: assign_nearest(cents[lbl], survivor_cents) for lbl in small}
    return _relabel([remap.get(l, l) for l in labels])
