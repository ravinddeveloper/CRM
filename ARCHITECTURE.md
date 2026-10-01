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
        ├── apps.scheduling     live classes, appointments, memberships and attendance
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

### Business sessions and attendance

`apps.scheduling` handles bookable live, in-person, hybrid, and appointment sessions; capacity and waitlists; optional course-enrollment or membership gates; member attendance; and employee time-clock records. Platform-level business type, public terms, base-site coordinates, geofence radius, accuracy tolerance, attendance windows, and whether each role requires location are configured in Platform Settings. A session can supply its own attendance coordinates and radius. Check-in stores the verified distance and accuracy rather than raw device coordinates.

Browser geolocation is device-reported and can be spoofed. The server validates coordinates and applies the geofence, but this is a practical attendance control rather than payroll-grade proof of physical presence. Stronger assurance requires trusted on-site hardware or manager review.

### Platform identity and invoices

`PlatformSettings` is a singleton editable in Django Admin under **Common → Platform settings**. The shared context processor supplies its public branding and validated color palette to website templates. The palette centralizes primary/accent, page and surface, text and border, semantic status, and invoice colors; shared CSS maps the existing utility classes to the configured values. Email templates and both invoice renderers read the same settings record. Environment values in `config/settings/base.py` provide defaults before the record is configured.

## Data ownership

Each domain app owns its schema and migrations. Cross-domain operations should call the owning app's service rather than duplicate rules in templates or unrelated views. `apps.common` contains only shared concerns; it should not become a catch-all for course, payment, or enrollment business logic.

## Configuration boundaries

- Secrets, infrastructure endpoints, and deployment-specific settings belong in environment variables.
- Public presentation and billing identity belong in `PlatformSettings` and can be changed without deployment.
- Paid media stays behind `apps.storage` and authorization checks in learning/resource views.
- Payment-specific code stays under `apps.payments.providers`; order fulfillment is a server-side operation.

## Local architecture maintenance

When adding a domain, keep its models, migrations, admin, API, and service logic together under `apps/<domain>/`. Add URL routing in `config/urls.py` or `config/api_urls.py`, update this map, and document new environment variables in `.env.example` and `README.md`.
