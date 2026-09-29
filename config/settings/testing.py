"""Testing settings."""
from .base import *

DEBUG = False
TESTING = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Disable caching in tests
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}

# Celery eager in tests
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Use in-memory email
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Use local storage in tests
STORAGE_BACKEND = "local"

# Disable rate limiting
RATELIMIT_ENABLE = False

# Fast password hashing in tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Disable CSRF in tests
MIDDLEWARE = [m for m in MIDDLEWARE if "csrf" not in m.lower()]

# Test payment keys
RAZORPAY_KEY_ID = "test_key_id"
RAZORPAY_KEY_SECRET = "test_key_secret"
RAZORPAY_WEBHOOK_SECRET = "test_webhook_secret"
STRIPE_SECRET_KEY = "sk_test_dummy"
STRIPE_WEBHOOK_SECRET = "whsec_test"

# Tax disabled by default in test suite
TAX_ENABLED = False
