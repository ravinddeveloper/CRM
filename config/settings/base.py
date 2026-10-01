"""
Base Django settings for the LMS platform.
All environments inherit from this file.
"""

from datetime import timedelta
from pathlib import Path

import dj_database_url
from decouple import Csv, config
from infrastructure.database.sql import build_sql_database_url

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
SECRET_KEY = config("SECRET_KEY", default="changeme-insecure-key-do-not-use-in-production")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "django.contrib.sitemaps",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "django_filters",
    "drf_spectacular",
    "django_htmx",
    "corsheaders",
    "storages",
    "django_celery_beat",
    "django_celery_results",
    "django_extensions",
]

LOCAL_APPS = [
    "apps.common",
    "apps.accounts",
    "apps.courses",
    "apps.lectures",
    "apps.enrollments",
    "apps.progress",
    "apps.orders",
    "apps.payments",
    "apps.storage",
    "apps.reviews",
    "apps.coupons",
    "apps.notifications",
    "apps.analytics",
    "apps.certificates",
    "apps.audit",
    "apps.scheduling",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "apps.common.middleware.AuditLogMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.common.context_processors.global_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASE_URL = build_sql_database_url(
    database_url=config("DATABASE_URL", default=""),
    db_host=config("DB_HOST", default=""),
    db_port=config("DB_PORT", default=5432, cast=int),
    db_name=config("DB_NAME", default="myportal"),
    db_user=config("DB_USER", default=""),
    db_password=config("DB_PASSWORD", default=""),
    sqlite_url=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
)
DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboard:redirect"
LOGOUT_REDIRECT_URL = "marketplace:course_list"

# Session configuration
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7  # 1 week
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=False, cast=bool)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"

# CSRF
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=False, cast=bool)
CSRF_COOKIE_HTTPONLY = True

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = config("TIME_ZONE", default="Asia/Kolkata")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & Media Files
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_BACKEND = config("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = config("EMAIL_HOST", default="localhost")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="LMS Platform <noreply@lms.local>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# ---------------------------------------------------------------------------
# Cache (Redis)
# ---------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": config("REDIS_URL", default="redis://localhost:6379/1"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        "KEY_PREFIX": "lms",
        "TIMEOUT": 300,
    }
}

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = config("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = "django-db"
CELERY_CACHE_BACKEND = "default"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_RESULT_SERIALIZER = "json"
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_BEAT_SCHEDULE = {
    "drain-enrollment-mongo-outbox": {
        "task": "apps.enrollments.tasks.drain_pending_enrollment_sync_events",
        "schedule": 60.0,
    },
    "drain-notification-mongo-outbox": {
        "task": "apps.notifications.tasks.drain_pending_notification_sync_events",
        "schedule": 60.0,
    },
    "drain-account-mongo-outbox": {
        "task": "apps.accounts.tasks.drain_pending_account_sync_events",
        "schedule": 60.0,
    },
    "drain-course-catalog-mongo-outbox": {
        "task": "apps.courses.tasks.drain_pending_catalog_sync_events",
        "schedule": 60.0,
    },
}

# ---------------------------------------------------------------------------
# REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardResultsPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.common.exceptions.custom_exception_handler",
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
}

# ---------------------------------------------------------------------------
# JWT Settings
# ---------------------------------------------------------------------------
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ---------------------------------------------------------------------------
# API Documentation
# ---------------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    "TITLE": "LMS Platform API",
    "DESCRIPTION": "Production-ready Learning Management System API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v[0-9]",
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", default="http://localhost:3000", cast=Csv())
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# Object Storage
# ---------------------------------------------------------------------------
STORAGE_BACKEND = config("STORAGE_BACKEND", default="local")  # local | minio | s3 | azure
S3_ENDPOINT_URL = config("S3_ENDPOINT_URL", default="")
S3_ACCESS_KEY = config("S3_ACCESS_KEY", default="")
S3_SECRET_KEY = config("S3_SECRET_KEY", default="")
S3_BUCKET_NAME = config("S3_BUCKET_NAME", default="lms-content")
S3_REGION = config("S3_REGION", default="us-east-1")
S3_SIGNED_URL_EXPIRY = config("S3_SIGNED_URL_EXPIRY", default=3600, cast=int)  # 1 hour
AZURE_ACCOUNT_NAME = config("AZURE_ACCOUNT_NAME", default="")
AZURE_ACCOUNT_KEY = config("AZURE_ACCOUNT_KEY", default="")
AZURE_CONTAINER = config("AZURE_CONTAINER", default="lms-content")
AZURE_CONNECTION_STRING = config("AZURE_CONNECTION_STRING", default="")
AZURE_CUSTOM_DOMAIN = config("AZURE_CUSTOM_DOMAIN", default="")
AZURE_SIGNED_URL_EXPIRY = config("AZURE_SIGNED_URL_EXPIRY", default=3600, cast=int)

# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------
PAYMENT_PROVIDER = config("PAYMENT_PROVIDER", default="razorpay")

RAZORPAY_KEY_ID = config("RAZORPAY_KEY_ID", default="")
RAZORPAY_KEY_SECRET = config("RAZORPAY_KEY_SECRET", default="")
RAZORPAY_WEBHOOK_SECRET = config("RAZORPAY_WEBHOOK_SECRET", default="")

STRIPE_SECRET_KEY = config("STRIPE_SECRET_KEY", default="")
STRIPE_PUBLISHABLE_KEY = config("STRIPE_PUBLISHABLE_KEY", default="")
STRIPE_WEBHOOK_SECRET = config("STRIPE_WEBHOOK_SECRET", default="")

# ---------------------------------------------------------------------------
# Learning / Progress
# ---------------------------------------------------------------------------
LECTURE_COMPLETION_THRESHOLD = config("LECTURE_COMPLETION_THRESHOLD", default=90, cast=int)  # percent
SIGNED_URL_EXPIRY_SECONDS = config("SIGNED_URL_EXPIRY_SECONDS", default=3600, cast=int)

# ---------------------------------------------------------------------------
# Tax
# ---------------------------------------------------------------------------
TAX_RATE = config("TAX_RATE", default="0.18")  # 18% GST
TAX_ENABLED = config("TAX_ENABLED", default=True, cast=bool)

# ---------------------------------------------------------------------------
# Platform Settings
# ---------------------------------------------------------------------------
PLATFORM_NAME = config("PLATFORM_NAME", default="LearnPro")
PLATFORM_URL = config("PLATFORM_URL", default="http://localhost:8000")
SUPPORT_EMAIL = config("SUPPORT_EMAIL", default="support@lms.local")

# Deployment-level palette defaults. Platform Settings in Django Admin take
# precedence once configured; these values seed a new installation/admin record.
_PORTAL_COLOR_DEFAULTS = {
    "PRIMARY": "#4f46e5", "ACCENT": "#7c3aed", "BACKGROUND": "#030712",
    "SURFACE": "#111827", "RAISED_SURFACE": "#1f2937", "TEXT": "#f9fafb",
    "MUTED_TEXT": "#9ca3af", "BORDER": "#374151", "INVERSE_TEXT": "#ffffff",
    "SUCCESS": "#10b981", "WARNING": "#f59e0b", "ERROR": "#ef4444", "INFO": "#3b82f6",
    "INVOICE_BACKGROUND": "#ffffff", "INVOICE_SURFACE": "#f8fafc", "INVOICE_TEXT": "#1e293b",
    "INVOICE_MUTED_TEXT": "#64748b", "INVOICE_BORDER": "#e2e8f0",
}
for _color_name, _default_color in _PORTAL_COLOR_DEFAULTS.items():
    globals()[f"PORTAL_{_color_name}_COLOR"] = config(f"PORTAL_{_color_name}_COLOR", default=_default_color)

# ---------------------------------------------------------------------------
# Rate Limiting
# ---------------------------------------------------------------------------
RATELIMIT_USE_CACHE = "default"
RATELIMIT_ENABLE = config("RATELIMIT_ENABLE", default=True, cast=bool)
LOGIN_RATE_LIMIT = config("LOGIN_RATE_LIMIT", default="5/m")

# ---------------------------------------------------------------------------
# File Upload
# ---------------------------------------------------------------------------
MAX_VIDEO_SIZE_MB = config("MAX_VIDEO_SIZE_MB", default=2048, cast=int)  # 2GB
MAX_DOCUMENT_SIZE_MB = config("MAX_DOCUMENT_SIZE_MB", default=50, cast=int)  # 50MB
MAX_IMAGE_SIZE_MB = config("MAX_IMAGE_SIZE_MB", default=10, cast=int)  # 10MB

ALLOWED_VIDEO_TYPES = ["video/mp4", "video/webm", "video/ogg", "video/quicktime", "video/x-msvideo"]
ALLOWED_DOCUMENT_TYPES = [
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
]
ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"]

# ---------------------------------------------------------------------------
# Logging (base)
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "filters": {
        "require_debug_true": {
            "()": "django.utils.log.RequireDebugTrue",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
        },
        "apps": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "payments": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
}
