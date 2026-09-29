"""Accounts REST API URL patterns."""
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import api_views

urlpatterns = [
    path("register/", api_views.register_api_view, name="api_register"),
    path("login/", api_views.login_api_view, name="api_login"),
    path("logout/", api_views.logout_api_view, name="api_logout"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("profile/", api_views.profile_api_view, name="api_profile"),
    path("change-password/", api_views.change_password_api_view, name="api_change_password"),
    path("verify-email/", api_views.verify_email_api_view, name="api_verify_email"),
    path("forgot-password/", api_views.forgot_password_api_view, name="api_forgot_password"),
    path("reset-password/", api_views.reset_password_api_view, name="api_reset_password"),
]
