from django.contrib import admin

from apps.jobs.manager import job_manager
from apps.jobs.models import BackgroundJob, JobLog


class JobLogInline(admin.TabularInline):
    model = JobLog
    extra = 0
    fields = ("created_at", "stage", "level", "message", "duration_ms")
    readonly_fields = fields
    ordering = ("created_at",)
    can_delete = False


@admin.register(BackgroundJob)
class BackgroundJobAdmin(admin.ModelAdmin):
    list_display = (
        "id", "job_type", "pipeline", "status", "priority", "progress",
        "current_stage", "attempts", "queue_name", "created_at",
    )
    list_filter = ("job_type", "pipeline", "status", "priority", "queue_name")
    search_fields = ("id", "error_message", "worker_id")
    readonly_fields = (
        "created_at", "updated_at", "started_at", "finished_at",
        "cancelled_at", "duration_ms", "locked_at", "stack_trace",
    )
    inlines = [JobLogInline]
    actions = ["admin_retry", "admin_cancel", "admin_pause", "admin_resume", "admin_requeue"]

    @admin.action(description="Retry selected failed/cancelled jobs")
    def admin_retry(self, request, queryset):
        for job in queryset:
            job_manager.retry(job)

    @admin.action(description="Cancel selected jobs")
    def admin_cancel(self, request, queryset):
        for job in queryset:
            job_manager.cancel(job)

    @admin.action(description="Pause selected jobs")
    def admin_pause(self, request, queryset):
        for job in queryset:
            job_manager.pause(job)

    @admin.action(description="Resume selected jobs")
    def admin_resume(self, request, queryset):
        for job in queryset:
            job_manager.resume(job)

    @admin.action(description="Requeue selected jobs from scratch")
    def admin_requeue(self, request, queryset):
        for job in queryset:
            job_manager.requeue(job)


@admin.register(JobLog)
class JobLogAdmin(admin.ModelAdmin):
    list_display = ("job", "stage", "level", "message", "duration_ms", "created_at")
    list_filter = ("level", "stage")
    search_fields = ("job__id", "message")
