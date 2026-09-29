"""Teacher dashboard URL patterns."""
from django.urls import path

from apps.courses import teacher_views as views

app_name = "teacher"

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("courses/", views.course_list_view, name="course_list"),
    path("courses/create/", views.course_create_view, name="course_create"),
    path("courses/<uuid:course_id>/", views.course_edit_view, name="course_edit"),
    path("courses/<uuid:course_id>/publish/", views.course_publish_view, name="course_publish"),
    path("courses/<uuid:course_id>/unpublish/", views.course_unpublish_view, name="course_unpublish"),
    path("courses/<uuid:course_id>/sections/", views.section_list_view, name="sections"),
    path("courses/<uuid:course_id>/sections/create/", views.section_create_view, name="section_create"),
    path("sections/<uuid:section_id>/lectures/create/", views.lecture_create_view, name="lecture_create"),
    path("lectures/<uuid:lecture_id>/", views.lecture_edit_view, name="lecture_edit"),
    path("lectures/<uuid:lecture_id>/upload-video/", views.video_upload_view, name="video_upload"),
    path("lectures/<uuid:lecture_id>/upload-note/", views.note_upload_view, name="note_upload"),
    path("materials/<str:resource_type>/<uuid:resource_id>/delete/", views.material_delete_view, name="material_delete"),
    path("courses/<uuid:course_id>/students/", views.course_students_view, name="course_students"),
    path("analytics/", views.analytics_view, name="analytics"),
]
