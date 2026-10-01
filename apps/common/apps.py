"""Common app configuration."""
from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"
    verbose_name = "Common"

    def ready(self):
        # Validate the shared repository engine at Django startup so typos never
        # silently fall back to a different persistence implementation.
        from infrastructure.database.config import get_database_engine

        get_database_engine()
