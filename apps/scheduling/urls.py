from django.urls import path

from . import views

app_name = "scheduling"

urlpatterns = [
    path("sessions/", views.session_list, name="sessions"),
    path("sessions/<uuid:session_id>/book/", views.session_book, name="session_book"),
    path("sessions/<uuid:session_id>/check-in/", views.member_check_in, name="member_check_in"),
    path("bookings/<uuid:booking_id>/cancel/", views.session_cancel, name="session_cancel"),
    path("staff/attendance/", views.staff_attendance, name="staff_attendance"),
    path("staff/attendance/action/", views.staff_attendance_action, name="staff_attendance_action"),
]
