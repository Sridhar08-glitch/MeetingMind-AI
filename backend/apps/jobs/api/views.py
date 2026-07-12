"""Background-jobs API: list/retrieve + admin controls + metrics."""
from __future__ import annotations

from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.common.responses import error_response, success_response
from apps.jobs.api.filters import JobFilter
from apps.jobs.api.permissions import IsJobOwnerOrAdmin
from apps.jobs.api.serializers import JobDetailSerializer, JobLogSerializer, JobSerializer
from apps.jobs.enums import JobStatus
from apps.jobs.manager import job_manager
from apps.jobs.models import BackgroundJob
from apps.jobs.selectors import job_metrics, jobs_for_user


class JobViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Read jobs and run admin controls (retry/cancel/pause/resume/requeue)."""

    permission_classes = [IsAuthenticated, IsJobOwnerOrAdmin]
    filterset_class = JobFilter
    ordering_fields = ("created_at", "priority", "duration_ms", "status")
    ordering = ("-created_at",)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False) or not self.request.user.is_authenticated:
            return BackgroundJob.objects.none()
        return jobs_for_user(self.request.user)

    def get_serializer_class(self):
        return JobDetailSerializer if self.action == "retrieve" else JobSerializer

    # --- controls --------------------------------------------------------
    def _controlled(self, request, apply, message: str):
        job = self.get_object()
        apply(job)
        job.refresh_from_db()
        return success_response(data=JobSerializer(job).data, message=message)

    @action(detail=True, methods=["post"])
    def retry(self, request: Request, pk=None):
        job = self.get_object()
        if job.status not in {JobStatus.FAILED, JobStatus.CANCELED}:
            return error_response("Only failed or cancelled jobs can be retried.",
                                  code="invalid_state", status=409)
        job_manager.retry(job)
        job.refresh_from_db()
        return success_response(data=JobSerializer(job).data, message="Job re-queued.")

    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, pk=None):
        job = self.get_object()
        if job.is_terminal:
            return error_response("Job has already finished.", code="invalid_state", status=409)
        return self._controlled(request, job_manager.cancel, "Cancellation requested.")

    @action(detail=True, methods=["post"])
    def pause(self, request: Request, pk=None):
        return self._controlled(request, job_manager.pause, "Job paused.")

    @action(detail=True, methods=["post"])
    def resume(self, request: Request, pk=None):
        return self._controlled(request, job_manager.resume, "Job resumed.")

    @action(detail=True, methods=["post"])
    def requeue(self, request: Request, pk=None):
        return self._controlled(request, job_manager.requeue, "Job re-queued from scratch.")

    # --- reads -----------------------------------------------------------
    @action(detail=True, methods=["get"])
    def logs(self, request: Request, pk=None):
        job = self.get_object()
        data = JobLogSerializer(job.job_logs.all(), many=True).data
        return success_response(data=data)

    @action(detail=True, methods=["get"])
    def timeline(self, request: Request, pk=None):
        job = self.get_object()
        return success_response(data={
            "job": JobSerializer(job).data,
            "logs": JobLogSerializer(job.job_logs.all(), many=True).data,
            "retries": job.metadata.get("retries", []),
        })


class JobMetricsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        return success_response(data=job_metrics(request.user))
