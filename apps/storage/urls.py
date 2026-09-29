"""Storage URLs for serving private signed files in development."""
from django.urls import path

from . import views

app_name = "storage"

urlpatterns = [
    path("", views.private_media_view, name="private_media"),
]
