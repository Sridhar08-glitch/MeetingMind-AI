from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BenchmarkConfigViewSet,
    BenchmarkDatasetViewSet,
    BenchmarkRecordingViewSet,
    BenchmarkRunViewSet,
)

app_name = "benchmarks"

router = DefaultRouter()
router.register("datasets", BenchmarkDatasetViewSet, basename="benchmark-dataset")
router.register("recordings", BenchmarkRecordingViewSet, basename="benchmark-recording")
router.register("configs", BenchmarkConfigViewSet, basename="benchmark-config")
router.register("runs", BenchmarkRunViewSet, basename="benchmark-run")

urlpatterns = [
    path("", include(router.urls)),
]
