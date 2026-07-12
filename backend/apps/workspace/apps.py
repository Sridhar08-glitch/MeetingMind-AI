from django.apps import AppConfig


class WorkspaceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.workspace"
    verbose_name = "Workspace"

    def ready(self) -> None:
        from apps.jobs.events import event_bus
        from apps.workspace import subscribers

        subscribers.register(event_bus)
