"""Jobs URL routes mounted under /api/jobs/."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.jobs.api.views import JobMetricsView, JobViewSet

app_name = "jobs"

router = DefaultRouter()
router.register("", JobViewSet, basename="job")

urlpatterns = [
    path("metrics/", JobMetricsView.as_view(), name="metrics"),
    path("", include(router.urls)),
]
