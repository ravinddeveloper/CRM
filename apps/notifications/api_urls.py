from django.urls import path

from apps.notifications.api_views import (
    MarkNotificationReadAPIView,
    NotificationListAPIView,
)

app_name = "notifications_api"

urlpatterns = [
    path("", NotificationListAPIView.as_view(), name="notification_list"),
    path("<uuid:pk>/read/", MarkNotificationReadAPIView.as_view(), name="mark_read"),
]
