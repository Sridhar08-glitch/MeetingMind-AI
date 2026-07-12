"""Run a diarization benchmark from the CLI, with an optional threshold sweep.

Examples:
    python manage.py run_benchmark --user demo@meetingmind.ai --dataset "Public panels"
    python manage.py run_benchmark --user demo@meetingmind.ai --dataset <id> \
        --threshold-sweep 0.4,0.5,0.6 --label "sweep-2026-07"

Re-clusters the persisted segment embeddings (no re-transcription), scores against
each recording's ground truth, and prints the per-config comparison. Honest by
construction: public-approximate recordings are labelled as such in the output.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.benchmarks.models import BenchmarkDataset
from apps.benchmarks.services import runner


class Command(BaseCommand):
    help = "Run a speaker-diarization benchmark over a dataset (optionally sweeping thresholds)."

    def add_arguments(self, parser):
        parser.add_argument("--user", required=True, help="Owner email.")
        parser.add_argument("--dataset", required=True, help="Dataset id, slug, or name.")
        parser.add_argument("--threshold-sweep", default="", help="Comma-separated cluster thresholds.")
        parser.add_argument("--label", default="", help="Optional run label.")

    def handle(self, *args, **opts):
        try:
            owner = User.objects.get(email=opts["user"])
        except User.DoesNotExist as exc:
            raise CommandError(f"No user {opts['user']!r}") from exc

        key = opts["dataset"]
        qs = BenchmarkDataset.objects.filter(owner=owner)
        dataset = (
            qs.filter(id=key).first()
            if _looks_like_uuid(key)
            else (qs.filter(slug=key).first() or qs.filter(name=key).first())
        )
        if not dataset:
            raise CommandError(f"No dataset {key!r} for {owner.email}")

        configs = None
        sweep = [s.strip() for s in opts["threshold_sweep"].split(",") if s.strip()]
        if sweep:
            base = runner.default_config()
            configs = [{**base, "name": f"thr={t}", "cluster_threshold": float(t)} for t in sweep]

        self.stdout.write(f"Running benchmark on '{dataset.name}' ({dataset.recordings.count()} recordings)...")
        run = runner.run_benchmark(owner, dataset=dataset, configs=configs, label=opts["label"])

        self.stdout.write(self.style.SUCCESS(
            f"Run {run.id} — {run.status}. Scored {run.recordings_scored}/{run.recordings_total} recording(s). "
            f"Speaker-count accuracy: {run.speaker_count_accuracy}%  "
            f"over-merged={run.total_over_merged} over-split={run.total_over_split}"
        ))
        self.stdout.write(f"Provenance: engine={run.diarization_engine} stt={run.stt_provider} "
                          f"git={run.git_commit or 'n/a'}")
        for row in runner.compare_configs(run):
            self.stdout.write(
                f"  [{row['config_label']}] acc={row['speaker_count_accuracy']}%  "
                f"merged={row['total_over_merged']} split={row['total_over_split']}  "
                f"conf={row['avg_embedding_confidence']}  {row['avg_processing_ms']}ms/rec"
            )


def _looks_like_uuid(value: str) -> bool:
    import uuid

    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError):
        return False
