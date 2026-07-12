"""Owner-scoped API for the benchmarking suite.

CRUD for datasets / recordings / configs, read access to runs and their results.
Running a benchmark, importing public recordings, and config comparison are added
in the runner increment. Every queryset is filtered by ``request.user``.
"""
from __future__ import annotations

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from apps.common.responses import error_response, success_response

from apps.benchmarks.models import (
    BenchmarkConfig,
    BenchmarkDataset,
    BenchmarkRecording,
    BenchmarkRun,
)
from apps.benchmarks.services import runner

from .serializers import (
    BenchmarkConfigSerializer,
    BenchmarkDatasetSerializer,
    BenchmarkRecordingSerializer,
    BenchmarkRunDetailSerializer,
    BenchmarkRunSerializer,
)


class EnvelopeModelViewSet(viewsets.ModelViewSet):
    """ModelViewSet whose CRUD responses use the standard success envelope and
    whose objects are attributed to and scoped by the authenticated owner."""

    permission_classes = [IsAuthenticated]
    pagination_class = None  # these are small, admin-style lists — return them enveloped

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def perform_update(self, serializer):
        serializer.instance.set_acting_user(self.request.user)
        serializer.save()

    def list(self, request, *args, **kwargs):
        data = self.get_serializer(self.filter_queryset(self.get_queryset()), many=True).data
        return success_response(data=data)

    def retrieve(self, request, *args, **kwargs):
        return success_response(data=self.get_serializer(self.get_object()).data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return success_response(
            data=serializer.data, message="Created.", status=status.HTTP_201_CREATED
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return success_response(data=serializer.data, message="Updated.")

    def destroy(self, request, *args, **kwargs):
        self.get_object().delete()
        return success_response(message="Deleted.", status=status.HTTP_200_OK)


class BenchmarkDatasetViewSet(EnvelopeModelViewSet):
    serializer_class = BenchmarkDatasetSerializer
    filterset_fields = ("kind",)

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return BenchmarkDataset.objects.none()
        return BenchmarkDataset.objects.filter(owner=self.request.user)

    @action(detail=False, methods=["post"], url_path="seed-public")
    def seed_public(self, request):
        """Materialise the curated public benchmark catalogue (req 1). Recordings
        are created PENDING; import them explicitly. Public = approximate truth."""
        from apps.benchmarks.services import imports

        limit = request.data.get("limit")
        dataset = imports.seed_public_dataset(request.user, limit=int(limit) if limit else None)
        return success_response(
            data=BenchmarkDatasetSerializer(dataset).data,
            message="Public benchmark suite seeded (recordings pending import).",
            status=status.HTTP_201_CREATED,
        )


class BenchmarkRecordingViewSet(EnvelopeModelViewSet):
    serializer_class = BenchmarkRecordingSerializer
    filterset_fields = ("dataset", "format", "status", "ground_truth_type")

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return BenchmarkRecording.objects.none()
        return BenchmarkRecording.objects.filter(owner=self.request.user).select_related("meeting", "dataset")

    def perform_create(self, serializer):
        # The dataset must belong to the caller (owner-scoping across the FK).
        dataset = serializer.validated_data.get("dataset")
        if dataset and dataset.owner_id != self.request.user.id:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Dataset does not belong to you.")
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=["post"], url_path="import")
    def import_recording(self, request, pk=None):
        """Import a public recording through the Phase 14 pipeline (req 1)."""
        from apps.benchmarks.services import imports

        recording = self.get_object()
        media = request.data.get("requested_media", "audio")
        session = imports.import_recording(recording, requested_media=media)
        recording.refresh_from_db()
        data = self.get_serializer(recording).data
        data["import_session_id"] = str(session.id) if session else None
        return success_response(data=data, message="Import started." if session else "Import skipped.")

    @action(detail=False, methods=["post"], url_path="from-meeting")
    def from_meeting(self, request):
        """Register the caller's own processed meeting as a user-verified
        benchmark recording (req 2)."""
        from apps.benchmarks.services import imports
        from apps.meetings.models import Meeting

        meeting = Meeting.objects.filter(owner=request.user, id=request.data.get("meeting")).first()
        if not meeting:
            return error_response("Meeting not found.", code="not_found", status=status.HTTP_404_NOT_FOUND)
        dataset = None
        if request.data.get("dataset"):
            dataset = BenchmarkDataset.objects.filter(
                owner=request.user, id=request.data["dataset"]
            ).first()
        recording = imports.create_user_recording_from_meeting(
            request.user, meeting=meeting, dataset=dataset,
            name=request.data.get("name", ""),
            expected_speaker_count=request.data.get("expected_speaker_count"),
            known_participants=request.data.get("known_participants", []),
            meeting_type=request.data.get("meeting_type", ""),
            reference_segments=request.data.get("reference_segments", []),
        )
        return success_response(
            data=self.get_serializer(recording).data,
            message="Recording created.", status=status.HTTP_201_CREATED,
        )


class BenchmarkConfigViewSet(EnvelopeModelViewSet):
    serializer_class = BenchmarkConfigSerializer

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return BenchmarkConfig.objects.none()
        return BenchmarkConfig.objects.filter(owner=self.request.user)


class BenchmarkRunViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsAuthenticated]
    pagination_class = None
    filterset_fields = ("dataset", "status")

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return BenchmarkRun.objects.none()
        return BenchmarkRun.objects.filter(owner=self.request.user)

    def get_serializer_class(self):
        return BenchmarkRunDetailSerializer if self.action == "retrieve" else BenchmarkRunSerializer

    def list(self, request, *args, **kwargs):
        data = self.get_serializer(self.filter_queryset(self.get_queryset()), many=True).data
        return success_response(data=data)

    def retrieve(self, request, *args, **kwargs):
        return success_response(data=self.get_serializer(self.get_object()).data)

    def _resolve_configs(self, request) -> list[dict] | None:
        """Build the config sweep from posted config ids and/or inline config dicts."""
        configs: list[dict] = []
        for cid in request.data.get("config_ids", []) or []:
            cfg = BenchmarkConfig.objects.filter(owner=request.user, id=cid).first()
            if cfg:
                configs.append(cfg.as_dict())
        for inline in request.data.get("configs", []) or []:
            if isinstance(inline, dict):
                merged = {**runner.default_config(), **inline}
                configs.append(merged)
        return configs or None

    @action(detail=False, methods=["post"], url_path="run")
    def run(self, request):
        """Execute a benchmark over a dataset under one or more configs (req 6)."""
        dataset_id = request.data.get("dataset")
        dataset = BenchmarkDataset.objects.filter(owner=request.user, id=dataset_id).first()
        if not dataset:
            return error_response("Dataset not found.", code="not_found", status=status.HTTP_404_NOT_FOUND)
        configs = self._resolve_configs(request)
        run = runner.run_benchmark(
            request.user, dataset=dataset, configs=configs, label=request.data.get("label", "")
        )
        return success_response(
            data=BenchmarkRunDetailSerializer(run).data,
            message="Benchmark completed.", status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"], url_path="compare")
    def compare(self, request, pk=None):
        """Per-config comparison report for a run (tuning harness output, req 6)."""
        run = self.get_object()
        return success_response(data={"run": str(run.id), "comparison": runner.compare_configs(run)})
