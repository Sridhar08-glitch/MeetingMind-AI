"""WebSocket URL routing for live meetings."""
from __future__ import annotations

from django.urls import path

from apps.meetings.live.consumer import LiveMeetingConsumer

websocket_urlpatterns = [
    path("ws/meetings/live/", LiveMeetingConsumer.as_asgi()),
]
