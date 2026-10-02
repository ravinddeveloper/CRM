"""URL patterns for announcements and notifications."""
from django.urls import path
from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.announcement_list, name="announcement_list"),
    path("<uuid:announcement_id>/", views.announcement_detail, name="announcement_detail"),
]
