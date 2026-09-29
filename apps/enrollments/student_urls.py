from django.urls import path

from apps.accounts.student_views import student_dashboard_view, student_orders_view

app_name = "student"

urlpatterns = [
    path("", student_dashboard_view, name="dashboard"),
    path("courses/", student_dashboard_view, name="courses"),
    path("orders/", student_orders_view, name="orders"),
]
