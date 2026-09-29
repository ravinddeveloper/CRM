"""Accounts URL configuration."""
from django.urls import path

from . import student_views, views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("register/", views.register_view, name="register"),
    path("verification-sent/", views.verification_sent_view, name="verification_sent"),
    path("verify-email/<uuid:token>/", views.verify_email_view, name="verify_email"),
    path("forgot-password/", views.forgot_password_view, name="forgot_password"),
    path("reset-password/<uuid:token>/", views.reset_password_view, name="reset_password"),
    path("profile/", views.profile_view, name="profile"),
    path("settings/", views.profile_view, name="settings"),
    path("change-password/", views.change_password_view, name="change_password"),
    path("dashboard/", student_views.student_dashboard_view, name="student_dashboard"),
    path("orders/", student_views.student_orders_view, name="my_orders"),
]
