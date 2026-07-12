from django.apps import AppConfig


class AgentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.agents"
    verbose_name = "AI Agents"

    def ready(self) -> None:
        # Register tools + agent profiles into their in-code registries.
        from apps.agents import agents as _agents  # noqa: F401
        from apps.agents import tools as _tools  # noqa: F401
