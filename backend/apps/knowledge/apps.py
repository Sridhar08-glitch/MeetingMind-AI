from django.apps import AppConfig


class KnowledgeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.knowledge"
    verbose_name = "Knowledge Hub"

    def ready(self) -> None:
        from apps.jobs.events import event_bus
        from apps.knowledge import subscribers

        subscribers.register(event_bus)
