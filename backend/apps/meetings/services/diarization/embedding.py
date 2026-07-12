"""EmbeddingDiarizationProvider — token-free local diarization (default).

Embeds each transcript segment with a local speaker encoder (SpeechBrain ECAPA,
public model — no HuggingFace token) and clusters the embeddings into speakers.
The per-cluster mean embedding is persisted for Phase 15B cross-meeting matching.

All heavy imports (torch / speechbrain / numpy / sklearn) are lazy so this module
loads even when the optional deps aren't installed; ``available()`` reports it.
"""
from __future__ import annotations

import logging
import wave

from django.conf import settings

from .base import DiarizationError, DiarizationProvider, DiarizationResult

logger = logging.getLogger("meetingmind.processing")

_ENCODER = None  # process-wide cache


class EmbeddingDiarizationProvider(DiarizationProvider):
    @property
    def name(self) -> str:
        return "embedding"

    @property
    def model_name(self) -> str:
        return getattr(settings, "DIARIZATION_EMBEDDING_MODEL", "speechbrain/spkrec-ecapa-voxceleb")

    @classmethod
    def available(cls) -> bool:
        try:
            import numpy  # noqa: F401
            import sklearn  # noqa: F401
            import speechbrain  # noqa: F401
            import torch  # noqa: F401
            return True
        except Exception:  # noqa: BLE001
            return False

    # --- model -----------------------------------------------------------
    def _encoder(self):
        global _ENCODER
        if _ENCODER is None:
            from speechbrain.inference.speaker import EncoderClassifier

            savedir = getattr(settings, "DIARIZATION_MODEL_DIR", None) or str(
                settings.BASE_DIR / "media" / "diarization-models"
            )
            _ENCODER = EncoderClassifier.from_hparams(source=self.model_name, savedir=savedir)
        return _ENCODER

    # --- audio -----------------------------------------------------------
    @staticmethod
    def _read_wav(path: str):
        import numpy as np

        with wave.open(path, "rb") as w:
            rate = w.getframerate()
            frames = w.readframes(w.getnframes())
        audio = np.frombuffer(frames, dtype=np.int16).astype("float32") / 32768.0
        return audio, rate

    def embed_segments(self, audio_path, segments) -> list[list[float]]:
        """One L2-normalized voice embedding per segment (reused by pyannote too)."""
        import numpy as np
        import torch

        audio, rate = self._read_wav(audio_path)
        encoder = self._encoder()
        vectors: list[list[float]] = []
        last = None
        with torch.no_grad():
            for start, end in segments:
                a = max(0, int(start * rate))
                b = min(len(audio), int(end * rate))
                if b - a < int(0.35 * rate) and last is not None:
                    vectors.append(last)  # too short to embed reliably — reuse prior
                    continue
                clip = audio[a:b] if b > a else audio[a:a + rate]
                wav = torch.from_numpy(np.ascontiguousarray(clip)).unsqueeze(0)
                emb = encoder.encode_batch(wav).squeeze().detach().cpu().numpy()
                emb = emb / (np.linalg.norm(emb) + 1e-9)
                last = emb.tolist()
                vectors.append(last)
        return vectors

    # --- diarize ---------------------------------------------------------
    def diarize(self, audio_path, *, segments, duration=None) -> DiarizationResult:
        if not segments:
            return DiarizationResult(segment_labels=[], provider=self.name, model=self.model_name)
        try:
            import numpy as np

            vectors = self.embed_segments(audio_path, segments)
        except Exception as exc:  # noqa: BLE001
            raise DiarizationError(f"embedding diarization unavailable: {exc}") from exc

        labels = self._cluster(np.array(vectors))
        embeddings = self._mean_embeddings(np.array(vectors), labels)
        return DiarizationResult(
            segment_labels=labels, embeddings=embeddings,
            segment_embeddings=vectors,  # per-segment vectors for 15B (SpeakerEmbedding rows)
            provider=self.name, model=self.model_name,
        )

    # --- clustering ------------------------------------------------------
    def _cluster(self, vectors) -> list[str]:
        import numpy as np
        from sklearn.cluster import AgglomerativeClustering

        n = len(vectors)
        if n == 1:
            return ["SPEAKER_00"]
        max_speakers = int(getattr(settings, "DIARIZATION_MAX_SPEAKERS", 10))
        threshold = float(getattr(settings, "DIARIZATION_CLUSTER_THRESHOLD", 0.65))
        # Cosine distance via agglomerative, auto number of clusters by threshold.
        model = AgglomerativeClustering(
            n_clusters=None, distance_threshold=threshold, metric="cosine", linkage="average",
        )
        raw = model.fit_predict(vectors)
        # Cap the speaker count if the threshold over-split.
        if len(set(raw)) > max_speakers:
            capped = AgglomerativeClustering(
                n_clusters=max_speakers, metric="cosine", linkage="average",
            )
            raw = capped.fit_predict(vectors)
        # Rename clusters to stable SPEAKER_NN in order of first appearance.
        order: dict[int, str] = {}
        labels: list[str] = []
        for c in raw:
            if c not in order:
                order[c] = f"SPEAKER_{len(order):02d}"
            labels.append(order[c])
        return labels

    @staticmethod
    def _mean_embeddings(vectors, labels) -> dict[str, list[float]]:
        import numpy as np

        out: dict[str, list[float]] = {}
        for label in set(labels):
            idx = [i for i, l in enumerate(labels) if l == label]
            mean = vectors[idx].mean(axis=0)
            mean = mean / (np.linalg.norm(mean) + 1e-9)
            out[label] = mean.tolist()
        return out
