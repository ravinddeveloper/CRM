"""REST API URL configuration."""
from django.urls import include, path

urlpatterns = [
    # Authentication
    path("auth/", include("apps.accounts.api_urls")),

    # Courses
    path("courses/", include("apps.courses.api_urls")),

    # Lectures
    path("lectures/", include("apps.lectures.api_urls")),

    # Enrollments
    path("enrollments/", include("apps.enrollments.api_urls")),

    # Progress
    path("progress/", include("apps.progress.api_urls")),

    # Orders
    path("orders/", include("apps.orders.api_urls")),

    # Payments
    path("payments/", include("apps.payments.api_urls")),

    # Reviews
    path("reviews/", include("apps.reviews.api_urls")),

    # Coupons
    path("coupons/", include("apps.coupons.api_urls")),

    # Notifications
    path("notifications/", include("apps.notifications.api_urls")),

    # Users
    path("users/", include("apps.accounts.users_api_urls")),

    # Analytics
    path("analytics/", include("apps.analytics.api_urls")),
]
