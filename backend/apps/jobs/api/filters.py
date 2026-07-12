"""Filters for the jobs list endpoint."""
from __future__ import annotations

import django_filters

from apps.jobs.models import BackgroundJob


class JobFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status")
    priority = django_filters.NumberFilter(field_name="priority")
    pipeline = django_filters.CharFilter(field_name="pipeline")
    job_type = django_filters.CharFilter(field_name="job_type")
    queue = django_filters.CharFilter(field_name="queue_name")
    created_after = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")
    # Jobs linked to a specific meeting (via MeetingJob).
    meeting = django_filters.UUIDFilter(method="filter_meeting")

    class Meta:
        model = BackgroundJob
        fields = ["status", "priority", "pipeline", "job_type", "queue"]

    def filter_meeting(self, queryset, name, value):
        return queryset.filter(meeting_link__meeting_id=value)
