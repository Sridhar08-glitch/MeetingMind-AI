"""Meetings URL routes mounted under /api/meetings/."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.meetings.api.chat import ConversationViewSet, SuggestedQuestionsView
from apps.meetings.api.imports import MediaImportViewSet
from apps.meetings.api.views import DashboardStatsView, MeetingViewSet

app_name = "meetings"

router = DefaultRouter()
router.register("conversations", ConversationViewSet, basename="conversation")
router.register("chat/suggested", SuggestedQuestionsView, basename="chat-suggested")
# Media import (Phase 14) — registered before the catch-all "" meeting routes.
router.register("import", MediaImportViewSet, basename="media-import")
router.register("", MeetingViewSet, basename="meeting")

urlpatterns = [
    path("dashboard/stats/", DashboardStatsView.as_view(), name="dashboard-stats"),
    path("", include(router.urls)),
]
