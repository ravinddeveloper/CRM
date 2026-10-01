"""Courses app configuration."""
from django.apps import AppConfig


class CoursesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.courses"
    verbose_name = "Courses"

    def ready(self):
        import apps.courses.sync_signals  # noqa: F401
