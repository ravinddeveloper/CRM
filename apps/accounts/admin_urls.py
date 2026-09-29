"""Admin panel URLs for accounts, courses, transactions, coupons, and enrollments."""
from django.urls import path

from . import admin_views

app_name = "admin_panel"

urlpatterns = [
    # Overview
    path("", admin_views.dashboard_view, name="dashboard"),

    # Course Management
    path("courses/", admin_views.course_list_view, name="course_list"),
    path("courses/create/", admin_views.course_create_view, name="course_create"),
    path("courses/<uuid:course_id>/edit/", admin_views.course_edit_view, name="course_edit"),
    path("courses/<uuid:course_id>/curriculum/", admin_views.course_curriculum_view, name="course_curriculum"),
    path("courses/<uuid:course_id>/publish/", admin_views.course_publish_toggle_view, name="course_toggle_publish"),
    path("courses/<uuid:course_id>/delete/", admin_views.course_delete_view, name="course_delete"),
    path("courses/<uuid:course_id>/sections/create/", admin_views.section_create_view, name="section_create"),
    path("courses/sections/<uuid:section_id>/delete/", admin_views.section_delete_view, name="section_delete"),
    path("courses/sections/<uuid:section_id>/lectures/create/", admin_views.lecture_create_view, name="lecture_create"),
    path("courses/lectures/<uuid:lecture_id>/delete/", admin_views.lecture_delete_view, name="lecture_delete"),
    path("courses/lectures/<uuid:lecture_id>/materials/upload/", admin_views.study_material_upload_view, name="study_material_upload"),
    path("courses/materials/<str:material_type>/<uuid:material_id>/delete/", admin_views.study_material_delete_view, name="study_material_delete"),

    # Transactions & Orders
    path("transactions/", admin_views.transaction_list_view, name="transaction_list"),
    path("transactions/<uuid:order_id>/", admin_views.transaction_detail_view, name="transaction_detail"),
    path("transactions/<uuid:order_id>/refund/", admin_views.transaction_refund_view, name="transaction_refund"),

    # Users Management
    path("users/", admin_views.user_list_view, name="user_list"),
    path("users/create/", admin_views.user_create_view, name="user_create"),
    path("users/<uuid:user_id>/", admin_views.user_detail_view, name="user_detail"),
    path("users/<uuid:user_id>/role/", admin_views.change_user_role_view, name="change_user_role"),
    path("users/<uuid:user_id>/suspend/", admin_views.suspend_user_view, name="suspend_user"),
    path("users/<uuid:user_id>/activate/", admin_views.activate_user_view, name="activate_user"),

    # Coupons & Promotions
    path("coupons/", admin_views.coupon_list_view, name="coupon_list"),
    path("coupons/create/", admin_views.coupon_create_view, name="coupon_create"),
    path("coupons/<uuid:coupon_id>/toggle/", admin_views.coupon_toggle_view, name="coupon_toggle"),
    path("coupons/<uuid:coupon_id>/delete/", admin_views.coupon_delete_view, name="coupon_delete"),

    # Enrollments Management
    path("enrollments/", admin_views.enrollment_list_view, name="enrollment_list"),
    path("enrollments/create/", admin_views.enrollment_create_view, name="enrollment_create"),
    path("enrollments/<uuid:enrollment_id>/toggle/", admin_views.enrollment_toggle_view, name="enrollment_toggle"),

    # Analytics, Audit & Reports
    path("analytics/", admin_views.analytics_view, name="analytics"),
    path("audit-logs/", admin_views.audit_log_view, name="audit_logs"),
    path("reports/", admin_views.reports_view, name="reports"),
    path("reports/revenue/", admin_views.revenue_report_view, name="revenue_report"),
    path("reports/students/", admin_views.student_report_view, name="student_report"),
]
