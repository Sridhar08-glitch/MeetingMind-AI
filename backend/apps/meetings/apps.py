from django.apps import AppConfig


class MeetingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.meetings"
    verbose_name = "Meetings"

    def ready(self) -> None:
        # Register the meeting-processing pipeline + stages (import side effect)
        # and subscribe the meetings domain to job-lifecycle events.
        from apps.jobs.events import event_bus
        from apps.meetings import pipeline  # noqa: F401 — registers stages/pipeline
        from apps.meetings import subscribers

        subscribers.register(event_bus)
