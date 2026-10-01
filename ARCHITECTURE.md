# EduFlow LMS architecture

This document describes the Django project as it exists in this repository. It is a domain-oriented Django monolith: domain apps own their models, views, APIs, and services, while one deployment serves the website and API.

## Request and service boundaries

```text
Browser / API client
        │
        ▼
config.urls ── public pages, account flows, dashboards, learning, commerce, API
        │
        ├── apps.accounts       identity, roles, profile and authentication
        ├── apps.courses        catalogue, categories, teacher course tools
        ├── apps.lectures       sections, lectures, notes, uploads
        ├── apps.orders         checkout orders and historical order lines
        ├── apps.payments       gateway adapters, callbacks and invoices
        ├── apps.enrollments    access grants and enrollment lifecycle
        ├── apps.progress       lecture playback and learning progress
        ├── apps.storage        local and object-storage adapters
        ├── apps.notifications  asynchronous email and notifications
        ├── apps.reviews        course reviews
        ├── apps.coupons        discounts and redemptions
        ├── apps.analytics      reporting queries and dashboard data
        ├── apps.certificates   completion certificates
        ├── apps.audit          administrative activity records
        └── apps.common         shared settings, middleware and utilities
        │
        ├── PostgreSQL (SQLite for local/testing configurations)
        ├── Redis / Celery for cache and background work
        └── StorageService → local, MinIO/S3-compatible, AWS S3, or Azure
```

## Main business flows

### Paid course access

1. The server creates an order from current course prices and any validated coupon.
2. A configured payment provider starts payment; browser success alone does not grant access.
3. Provider verification/callback processing updates payment state.
4. The order fulfillment service creates an enrollment after verified payment.
5. Learning and resource views check the current user's enrollment before returning paid content or temporary storage access.

### Learning progress

Lecture progress is stored per learner and lecture. The progress service owns position and completion updates; course-level progress is derived from lecture progress rather than an untrusted client flag.

### Platform identity and invoices

`PlatformSettings` is a singleton editable in Django Admin under **Common → Platform settings**. The shared context processor supplies its public branding to website templates. Invoice HTML and PDF generation read the same record. Environment values in `config/settings/base.py` provide defaults before the record is configured.

## Data ownership

Each domain app owns its schema and migrations. Cross-domain operations should call the owning app's service rather than duplicate rules in templates or unrelated views. `apps.common` contains only shared concerns; it should not become a catch-all for course, payment, or enrollment business logic.

## Configuration boundaries

- Secrets, infrastructure endpoints, and deployment-specific settings belong in environment variables.
- Public presentation and billing identity belong in `PlatformSettings` and can be changed without deployment.
- Paid media stays behind `apps.storage` and authorization checks in learning/resource views.
- Payment-specific code stays under `apps.payments.providers`; order fulfillment is a server-side operation.

## Local architecture maintenance

When adding a domain, keep its models, migrations, admin, API, and service logic together under `apps/<domain>/`. Add URL routing in `config/urls.py` or `config/api_urls.py`, update this map, and document new environment variables in `.env.example` and `README.md`.
