"""Development settings."""
import importlib.util

from .base import *

DEBUG = True

if importlib.util.find_spec("debug_toolbar"):
    INSTALLED_APPS += ["debug_toolbar"]
    MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware"] + MIDDLEWARE

INTERNAL_IPS = ["127.0.0.1", "localhost"]
ALLOWED_HOSTS = ["*"]

# Use SQLite for easy local development (override with DATABASE_URL for PostgreSQL)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Email to console in development
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Disable rate limiting in development
RATELIMIT_ENABLE = False

# Local file storage in development
STORAGE_BACKEND = "local"

# Relaxed security for development
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Development cache using in-memory
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# Celery runs synchronously in development (easier debugging)
# Comment this out to use real Celery with Redis
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

DEBUG_TOOLBAR_CONFIG = {
    "SHOW_TOOLBAR_CALLBACK": lambda request: DEBUG,
}
