# EduFlow LMS — Production-Ready Online Learning & Paid Course Platform

A secure, scalable, enterprise-grade learning management platform built with Django 5+, Django REST Framework, PostgreSQL, Redis, Celery, and Docker.

---

## Table of Contents

1. [Architectural Overview](#architectural-overview)
2. [Project Architecture Guide](#project-architecture-guide)
3. [Technology Stack](#technology-stack)
4. [User Roles & Permissions](#user-roles--permissions)
5. [Security Architecture](#security-architecture)
6. [Storage Abstraction (MinIO / AWS S3 / Azure)](#storage-abstraction)
7. [Payment Processing & Webhook Idempotency](#payment-processing)
8. [Student Learning Interface & Progress Tracking](#student-learning-interface)
9. [Local Development Setup](#local-development-setup)
10. [Running Celery & Background Jobs](#running-celery)
11. [Management Commands & Seeding Demo Data](#management-commands)
12. [Running the Automated Test Suite](#running-the-automated-test-suite)
13. [Docker & Production Deployment](#docker--production-deployment)
14. [API Documentation](#api-documentation)
15. [Backup & Maintenance Recommendations](#backup--maintenance-recommendations)

---

## 1. Architectural Overview

EduFlow LMS adheres to Clean Architecture and Domain-Driven Design principles:
- **Thin Views, Rich Domain Services**: All core business rules (orders, payment verification, coupon validation, enrollment granting, signed URL generation, progress calculations) reside in isolated service layers (`apps.<domain>.services`).
- **Zero Frontend Trust**: Course pricing, discount calculations, payment status verification, and progress completion thresholds are strictly enforced server-side.
- **Private Content Isolation**: Paid video files and resources are never served directly by Django static or exposed via permanent public URLs. Access is mediated by temporary, expiring HMAC-signed presigned URLs (60-120 minutes) issued only after verifying the student's active enrollment.
- **Webhook Idempotency**: Payment callbacks are validated against cryptographic provider signatures (HMAC-SHA256) and tracked in a `WebhookEvent` table to prevent replay attacks and duplicate enrollments.

```
                           ┌────────────────────────┐
                           │    Nginx Proxy / CDN   │
                           └───────────┬────────────┘
                                       │
                    ┌──────────────────┴──────────────────┐
                    ▼                                     ▼
        ┌───────────────────────┐             ┌───────────────────────┐
        │  Django Web / API     │             │  Static Assets        │
        │  (Gunicorn / WSGI)    │             │  (WhiteNoise/S3)      │
        └───────────┬───────────┘             └───────────────────────┘
                    │
         ┌──────────┼──────────┬──────────────┐
         ▼          ▼          ▼              ▼
    ┌─────────┐┌─────────┐┌─────────┐ ┌───────────────┐
    │Postgres ││  Redis  ││ Celery  │ │ Object Storage │
    │ 15+ DB  ││  Cache  ││ Workers │ │ (MinIO/S3/Az) │
    └─────────┘└─────────┘└────┬────┘ └───────▲───────┘
                               │              │
                               └──────────────┘ (Signed URLs)
```

---

## 2. Project Architecture Guide

See [ARCHITECTURE.md](ARCHITECTURE.md) for the repository-specific app map, request boundaries, payment-to-enrollment flow, and configuration ownership.

### Configure website identity and invoices

After creating a Django superuser and applying migrations, open `/django-admin/` and choose **Common → Platform settings**. Configure the public name, tagline, logo, favicon, theme color, support contact, legal business name, billing address, tax registration number, and invoice footer. The values apply to shared site branding, account pages, payment checkout labels, notification email names, and newly generated invoices. Existing invoices remain historical documents.

The logo and favicon are stored using Django's configured media storage. The production Nginx configuration serves only `/media/branding/` publicly; keep the general media directory private and use the protected storage flow for course content.

### Classes, memberships, and attendance

The **Classes, bookings and attendance** area in Django Admin manages live online, in-person, hybrid, and appointment sessions, instructors, capacities, waitlists, and attendance. Members can book at `/sessions/`; employees use `/staff/attendance/` to clock in and out. The staff role is assigned to an account by an administrator. Existing teachers can also use the employee time clock.

For a dance studio, gym, fitness business, or workshop provider, set the business type and terms in Platform Settings, add the desired site coordinates, choose the allowed geofence radius and location accuracy, then enable staff and/or member location checks. Each scheduled session can override the site coordinates/radius and can optionally require a linked paid course enrollment or active membership. Membership plans and member memberships are currently managed by staff in Django Admin; membership checkout and recurring billing are not connected to the payment gateway yet.

Location checks use browser-reported coordinates and are not proof against GPS spoofing. For payroll or regulated attendance, use a trusted on-site device or manager approval as an additional control.

## 3. Technology Stack

- **Backend**: Python 3.12+, Django 5.x / 6.x, Django REST Framework (DRF), `drf-spectacular` (OpenAPI 3.0)
- **Database**: PostgreSQL 15+ (production) / SQLite (isolated testing)
- **Cache & Message Broker**: Redis 7+
- **Asynchronous Task Queue**: Celery 5.x + Celery Beat
- **Storage**: Pluggable backend (Local / MinIO / AWS S3 / Azure Blob Storage) via `boto3` and `django-storages`
- **Frontend**: Django Templates, Tailwind CSS, Alpine.js, HTMX
- **WSGI / Web Server**: Gunicorn + Nginx reverse proxy + WhiteNoise

---

## 4. User Roles & Permissions

1. **Admin**:
   - Access to both the custom Admin Console (`/dashboard/admin/`) and Django Admin (`/django-admin/`).
   - Platform analytics, revenue reports, user activation/suspension, coupon management, audit log inspection.
2. **Teacher / Instructor**:
   - Dedicated Teacher Dashboard (`/dashboard/teacher/`).
   - Create and organize courses, modules/sections, and lectures.
   - Upload private lecture videos and notes/attachments.
   - View enrolled students and per-course revenue/completion metrics.
3. **Student / Subscriber**:
   - Dedicated Student Dashboard (`/dashboard/student/`).
   - Browse marketplace, search and filter courses by category/difficulty.
   - Secure checkout with coupon redemption and multiple payment providers (Razorpay / Stripe).
   - Dedicated dual-pane learning interface (`/learn/<course_slug>/`) with HTML5 video player, auto-resume playback, notes reader, and downloadable resources.
   - Review purchase history and download official PDF receipts (`/orders/`).

---

## 4. Security Architecture

- **Session & CSRF Hardening**: `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`, `X_FRAME_OPTIONS = "DENY"`.
- **Content Security Policy (CSP)**: Fine-grained script, style, font, and frame restrictions configured for Razorpay and Stripe SDKs.
- **Rate Limiting**: IP and user-based throttling on authentication endpoints (`/accounts/login/`, `/api/v1/auth/login/`) to stop credential-stuffing.
- **IDOR Protection**: Object-level authorization checks on all lecture views, video streaming requests, resource downloads, and invoice generation.

---

## 5. Storage Abstraction

All file storage operations pass through the unified `StorageService` interface (`apps/storage/service.py`):

```python
from apps.storage.service import StorageService

# Generate a temporary signed expiring URL for video streaming
signed_url = StorageService.get_presigned_url(storage_key="videos/course_1/lec_2.mp4", expires_in=7200)

# Upload private resource
storage_key = StorageService.upload_file(key="notes/doc.pdf", file_obj=uploaded_file, content_type="application/pdf")
```

Switch backends effortlessly via environment variable `STORAGE_BACKEND`:
- `local`: Development storage under `/media/` with temporary token verification
- `minio`: S3-compatible local Docker storage (`http://minio:9000`)
- `s3`: AWS S3 bucket with private ACL
- `azure`: Azure Blob Storage container

---

## 6. Payment Processing

The payment domain (`apps/payments/`) abstracts payment gateways via `BasePaymentProvider`:
- **Razorpay**: Orders API, checkout modal, HMAC-SHA256 signature verification.
- **Stripe**: PaymentIntents API, Elements, Webhook secret signature verification.

### Webhook Idempotency Flow:
```
Provider Webhook POST → Signature Validation → Check WebhookEvent (idempotency)
                                                      │
                       ┌──────────────────────────────┴──────────────────────────────┐
                       ▼                                                             ▼
                 Already Processed                                              New Event
                       │                                                             │
                  Return 200 OK                                             Record in WebhookEvent
                                                                                     │
                                                                           Fulfill Order & Enroll
                                                                                     │
                                                                           Generate PDF Invoice
```

---

## 7. Student Learning Interface

The learning room (`/learn/<course_slug>/lecture/<lecture_id>/`) features:
- **Responsive Dual-Pane**: Video player and lecture controls on left; collapsible curriculum module accordion on right.
- **Resume Playback**: Remembers playback position (`video_position_seconds`) and prompts user to resume where they left off.
- **Heartbeat Synchronization**: Automatic ping to `/api/v1/progress/heartbeat/` every 15 seconds to track watch time and calculate completion percentages accurately.
- **Auto-Completion**: Automatically marks lectures complete when the student passes the configured threshold (default: 90% watched).
- **Certificate Issuance**: Automatically triggers Celery task to generate verification code and completion record when 100% of lectures are finished.

---

## 8. Local Development Setup

### Prerequisites
- Python 3.12+ (or `uv` package manager)
- Git

### 1. Clone repository & create virtual environment
```bash
git clone <repository_url>
cd CRM
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 2. Install dependencies
```bash
pip install -r requirements/base.txt -r requirements/development.txt
```

### 3. Setup environment configuration
```bash
cp .env.example .env
```

### 4. Run database migrations
```bash
python manage.py migrate --settings=config.settings.development
```

### 5. Seed realistic demo data
```bash
python manage.py seed_demo --settings=config.settings.development
```

### 6. Start development server
```bash
python manage.py runserver --settings=config.settings.development
```
Access the application at `http://127.0.0.1:8000/`.

---

## 9. Running Celery & Background Jobs

In production or local development with Redis running:
```bash
# Start Celery Worker
celery -A config.celery worker --loglevel=info --concurrency=4

# Start Celery Beat (Periodic task scheduler)
celery -A config.celery beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

---

## 10. Management Commands

| Command | Purpose |
|---|---|
| `python manage.py seed_demo` | Populates demo Admin, Teacher, Student, Categories, Courses, Lectures, and Coupons |
| `python manage.py verify_storage` | Tests file upload, presence, presigned URL signing, and deletion on active backend |
| `python manage.py check_payment_configuration` | Inspects Razorpay and Stripe API keys and webhook credentials |
| `python manage.py cleanup_expired_data` | Cleans up expired email verification tokens, password resets, and 30+ day old webhooks |

---

## 11. Running the Automated Test Suite

Automated unit, security, integration, and API test suites are located under `tests/`. Run them in the configured test environment to check the current project state:

```bash
# Run complete test suite
pytest --ds=config.settings.testing

# Run with verbose output
pytest -v --ds=config.settings.testing

# Run specific suite
pytest tests/security/test_security.py --ds=config.settings.testing
pytest tests/integration/test_flows.py --ds=config.settings.testing
pytest tests/api/test_api_endpoints.py --ds=config.settings.testing
```

---

## 12. Docker & Production Deployment

A multi-stage `Dockerfile` and `docker-compose.yml` are provided out of the box:

```bash
# Build and spin up the complete production cluster
docker-compose up -d --build

# Run initial migrations
docker-compose exec web python manage.py migrate --settings=config.settings.production

# Collect static assets
docker-compose exec web python manage.py collectstatic --noinput --settings=config.settings.production

# Seed initial data (optional)
docker-compose exec web python manage.py seed_demo
```

### Docker Services:
- `web`: Django WSGI application powered by Gunicorn with 4 workers.
- `postgres`: PostgreSQL 15 database with persistent volume.
- `redis`: Redis 7 cache & message broker.
- `celery`: Async workers processing invoices, emails, and notifications.
- `celery-beat`: Database-backed cron scheduler.
- `minio` + `minio-init`: Local S3-compatible private object storage bucket.
- `nginx`: Reverse proxy routing requests and serving cached static media.

---

## 13. API Documentation

Interactive OpenAPI 3.0 API documentation is available out of the box:
- **Swagger UI**: `/api/docs/swagger/`
- **ReDoc**: `/api/docs/redoc/`
- **OpenAPI Schema (JSON)**: `/api/docs/schema/`

---

## 14. Demo Credentials

After running `python manage.py seed_demo`:

| Role | Email | Password | Dashboard URL |
|---|---|---|---|
| **Admin** | `admin@eduflow.local` | `Admin1234!` | `/dashboard/admin/` |
| **Teacher** | `teacher@eduflow.local` | `Teacher1234!` | `/dashboard/teacher/` |
| **Student** | `student@eduflow.local` | `Student1234!` | `/dashboard/student/` |

---

## 15. Backup & Maintenance Recommendations

1. **Database Backups**:
   - Perform daily automated `pg_dump` backups with point-in-time recovery (PITR) enabled.
   - Example cron job: `pg_dump -U $POSTGRES_USER -h localhost -Fc $POSTGRES_DB > /backups/lms_$(date +%Y%m%d_%H%M%S).dump`.
2. **Object Storage Replication**:
   - Enable S3 Bucket Versioning and Cross-Region Replication for course video buckets.
3. **Log Rotation**:
   - Docker container logs and `/var/log/lms/app.log` are configured with a 50MB ceiling and 10 backup archives.
