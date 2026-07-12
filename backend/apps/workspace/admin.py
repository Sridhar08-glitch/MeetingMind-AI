from django.contrib import admin

from apps.workspace.models import (
    AISuggestion,
    Decision,
    FollowUp,
    Issue,
    Milestone,
    Note,
    Notification,
    Project,
    Report,
    Risk,
    ActivityLog,
    Task,
    TaskAttachment,
    TaskComment,
    Workspace,
)


@admin.register(AISuggestion)
class AISuggestionAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "suggestion_type", "status", "confidence", "confidence_score", "meeting")
    list_filter = ("suggestion_type", "status", "confidence")
    search_fields = ("title", "quote")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "status", "priority", "assignee", "created_by_ai", "meeting")
    list_filter = ("status", "priority", "category", "created_by_ai")
    search_fields = ("title", "description")


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "issue_type", "severity", "status", "created_by_ai")
    list_filter = ("issue_type", "severity", "status")


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "report_type", "version", "is_current", "provider")
    list_filter = ("report_type", "is_current")


admin.site.register(Workspace)
admin.site.register(TaskComment)
admin.site.register(TaskAttachment)
admin.site.register(ActivityLog)
admin.site.register(Project)
admin.site.register(Milestone)
admin.site.register(Decision)
admin.site.register(Risk)
admin.site.register(FollowUp)
admin.site.register(Note)
admin.site.register(Notification)
