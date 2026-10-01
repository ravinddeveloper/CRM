"""PythonAnywhere deployment settings.

Optimized for PythonAnywhere hosting:
- Uses in-memory caching (LocMemCache) since Redis is not available on free tier.
- Runs Celery tasks synchronously (CELERY_TASK_ALWAYS_EAGER) without separate daemon.
- Safe logging directory inside project folder (avoiding /var/log permissions issues).
- Automatically includes .pythonanywhere.com in ALLOWED_HOSTS and CSRF_TRUSTED_ORIGINS.
"""
from pathlib import Path
from decouple import Csv, config

from .base import *

DEBUG = config("DEBUG", default=False, cast=bool)

# Allowed Hosts & CSRF
ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default=".pythonanywhere.com,localhost,127.0.0.1",
    cast=Csv(),
)

CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS",
    default="https://*.pythonanywhere.com",
    cast=Csv(),
)

# HTTPS / Security
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"
REFERRER_POLICY = "strict-origin-when-cross-origin"

# Cache (LocMemCache by default; Redis can still be configured via REDIS_URL if using paid tier)
if config("USE_REDIS_CACHE", default=False, cast=bool):
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": config("REDIS_URL", default="redis://127.0.0.1:6379/1"),
            "KEY_PREFIX": "lms",
            "TIMEOUT": 300,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "pythonanywhere-lms-cache",
        }
    }

# Celery: Run tasks synchronously unless external worker is active
CELERY_TASK_ALWAYS_EAGER = config("CELERY_TASK_ALWAYS_EAGER", default=True, cast=bool)
CELERY_TASK_EAGER_PROPAGATES = True

# Storage: Local media by default unless cloud storage is set in .env
STORAGE_BACKEND = config("STORAGE_BACKEND", default="local")

# Static files
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Safe project logging
LOG_DIR = BASE_DIR / "logs"
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "app.log"),
            "maxBytes": 1024 * 1024 * 10,  # 10MB
            "backupCount": 5,
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {"handlers": ["console", "file"], "level": "ERROR"},
        "apps": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
        "payments": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
}
