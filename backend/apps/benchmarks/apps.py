from django.apps import AppConfig


class BenchmarksConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.benchmarks"
    verbose_name = "Benchmarks"

    def ready(self) -> None:
        # Keep benchmark ingestion in sync with the media-import lifecycle so a
        # recording's status follows its underlying import/pipeline run.
        from apps.jobs.events import event_bus

        from . import subscribers

        subscribers.register(event_bus)
