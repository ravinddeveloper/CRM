"""LMS Platform URL configuration."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path

from apps.courses.sitemaps import CourseSitemap
from apps.storage.views import gdrive_media_view

sitemaps = {
    "courses": CourseSitemap,
}

urlpatterns = [
    # Django admin
    path("django-admin/", admin.site.urls),

    # Public pages
    path("", include("apps.courses.urls.marketplace", namespace="marketplace")),

    # Authentication
    path("accounts/", include("apps.accounts.urls", namespace="accounts")),

    # Dashboards
    path("dashboard/", include("apps.common.dashboard_urls", namespace="dashboard")),
    path("dashboard/admin/", include("apps.accounts.admin_urls", namespace="admin_panel")),
    path("dashboard/teacher/", include("apps.courses.teacher_urls", namespace="teacher")),
    path("dashboard/student/", include("apps.enrollments.student_urls", namespace="student")),

    # Learning interface
    path("learn/", include("apps.progress.urls", namespace="learn")),

    # Business schedules, bookings, and attendance
    path("", include("apps.scheduling.urls", namespace="scheduling")),

    # Orders and payments
    path("orders/", include("apps.orders.urls", namespace="orders")),
    path("payments/", include("apps.payments.urls", namespace="payments")),

    # Notifications & Announcements
    path("notifications/", include("apps.notifications.urls", namespace="notifications")),
    path("announcements/", include("apps.notifications.urls", namespace="announcements")),

    # Certificates
    path("certificates/", include("apps.certificates.urls", namespace="certificates")),

    # REST API v1
    path("api/v1/", include("config.api_urls")),

    # API Documentation
    path("api/docs/", include("config.docs_urls")),

    # SEO
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="django.contrib.sitemaps.views.sitemap"),
    path("robots.txt", include("apps.common.robots_urls")),

    # Private object storage serving for development
    path("private-media/", include("apps.storage.urls")),

    # Google Drive media proxy (signed URLs issued by GoogleDriveStorageService)
    path("gdrive-media/", gdrive_media_view, name="gdrive_media"),
]

# Error handlers
handler400 = "apps.common.views.error_400"
handler403 = "apps.common.views.error_403"
handler404 = "apps.common.views.error_404"
handler500 = "apps.common.views.error_500"

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    try:
        import debug_toolbar
        urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
    except ImportError:
        pass
