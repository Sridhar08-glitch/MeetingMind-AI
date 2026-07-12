"""Root URL configuration for MeetingMind AI."""
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.common import health
from apps.common.demo_views import (
    DemoInfoView,
    DemoResetView,
    DemoSampleDownloadView,
    DemoSamplesView,
)
from apps.common.system_views import SystemInfoView
from apps.meetings.api.imports import MediaSourcesView
from apps.meetings.api.languages import LanguagesView

urlpatterns = [
    path("admin/", admin.site.urls),
    # Health checks (structured JSON).
    path("api/health/", health.health, name="health"),
    path("api/health/database/", health.health_database, name="health-database"),
    path("api/health/redis/", health.health_redis, name="health-redis"),
    path("api/health/storage/", health.health_storage, name="health-storage"),
    path("api/health/workers/", health.health_workers, name="health-workers"),
    # Demo Mode
    path("api/demo/info/", DemoInfoView.as_view(), name="demo-info"),
    path("api/demo/reset/", DemoResetView.as_view(), name="demo-reset"),
    path("api/demo/samples/", DemoSamplesView.as_view(), name="demo-samples"),
    path("api/demo/samples/<str:filename>/", DemoSampleDownloadView.as_view(), name="demo-sample-download"),
    # System status (read-only)
    path("api/system/info/", SystemInfoView.as_view(), name="system-info"),
    # Provider language capabilities (dynamic; no hardcoded list)
    path("api/languages/", LanguagesView.as_view(), name="languages"),
    # Media-import source capabilities (Phase 14; dynamic from active providers)
    path("api/media/sources/", MediaSourcesView.as_view(), name="media-sources"),
    # API
    path("api/auth/", include("apps.accounts.api.urls")),
    path("api/meetings/", include("apps.meetings.api.urls")),
    path("api/jobs/", include("apps.jobs.api.urls")),
    path("api/workspace/", include("apps.workspace.api.urls")),
    path("api/knowledge/", include("apps.knowledge.api.urls")),
    path("api/agents/", include("apps.agents.api.urls")),
    path("api/benchmarks/", include("apps.benchmarks.api.urls")),
    # API schema & docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
