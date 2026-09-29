"""Learning interface and lecture progress URLs."""
from django.urls import path

from . import views

app_name = "learn"

urlpatterns = [
    path("<slug:course_slug>/", views.course_learn_view, name="course"),
    path("<slug:course_slug>/lecture/<uuid:lecture_id>/", views.lecture_learn_view, name="lecture"),
    path("<slug:course_slug>/lecture/<uuid:lecture_id>/complete/", views.mark_complete_view, name="complete"),
    path(
        "<slug:course_slug>/lecture/<uuid:lecture_id>/resource/<str:resource_type>/<uuid:resource_id>/",
        views.download_resource_view,
        name="download_resource",
    ),

    # Student Note Taking & Uploads
    path("<slug:course_slug>/lecture/<uuid:lecture_id>/notes/save/", views.save_student_note_view, name="save_note"),
    path("<slug:course_slug>/lecture/<uuid:lecture_id>/notes/<uuid:note_id>/delete/", views.delete_student_note_view, name="delete_note"),
    path("<slug:course_slug>/lecture/<uuid:lecture_id>/notes/<uuid:note_id>/download/", views.download_student_note_file_view, name="download_note_file"),
]
