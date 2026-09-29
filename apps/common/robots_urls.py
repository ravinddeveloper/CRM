"""Robots.txt URL."""
from django.urls import path
from django.views.generic import TemplateView

urlpatterns = [
    path("", TemplateView.as_view(
        template_name="robots.txt",
        content_type="text/plain"
    ), name="robots"),
]
