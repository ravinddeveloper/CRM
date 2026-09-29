# ─────────────────────────────────────────────────────────────────────────────
# Django LMS – Multi-stage Dockerfile
# ─────────────────────────────────────────────────────────────────────────────
# Stages:
#   base        – shared Python base
#   development – dev tools + hot-reload
#   production  – optimised production image
# ─────────────────────────────────────────────────────────────────────────────

# ── Base stage ───────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

# Environment flags
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# OS-level dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements/base.txt requirements/base.txt
RUN pip install -r requirements/base.txt

COPY . .

# ── Development stage ─────────────────────────────────────────────────────────
FROM base AS development

COPY requirements/development.txt requirements/development.txt
RUN pip install -r requirements/development.txt

# Create non-root user for development
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# ── Production stage ──────────────────────────────────────────────────────────
FROM base AS production

# Install production-only dependencies (gunicorn is in base.txt)
RUN pip install gunicorn

# Create non-root user
RUN useradd -m -u 1000 appuser \
    && mkdir -p /app/staticfiles /app/media \
    && chown -R appuser:appuser /app

USER appuser

# Collect static files
RUN python manage.py collectstatic --noinput --settings=config.settings.production || true

EXPOSE 8000

# Gunicorn with 4 workers; override via GUNICORN_CMD_ARGS env var
CMD ["gunicorn", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "4", \
     "--worker-class", "sync", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "config.wsgi:application"]
