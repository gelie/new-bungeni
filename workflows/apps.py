from django.apps import AppConfig


class WorkflowsConfig(AppConfig):
    name = "workflows"

    def ready(self):
        import workflows.signals  # noqa: F401
