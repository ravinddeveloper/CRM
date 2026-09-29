from django.urls import path

from apps.progress.api import views

app_name = "progress_api"

urlpatterns = [
    # Lecture position
    path("lecture/<uuid:lecture_id>/position/", views.update_video_position, name="update_position"),
    path("lectures/<uuid:lecture_id>/position/", views.update_video_position),

    # Lecture resume
    path("lecture/<uuid:lecture_id>/resume/", views.get_resume_position, name="get_resume_position"),
    path("lectures/<uuid:lecture_id>/resume/", views.get_resume_position),

    # Lecture complete
    path("lecture/<uuid:lecture_id>/complete/", views.mark_lecture_complete, name="mark_complete"),
    path("lectures/<uuid:lecture_id>/complete/", views.mark_lecture_complete),

    # Course progress
    path("course/<uuid:course_id>/", views.get_course_progress, name="course_progress"),
    path("courses/<uuid:course_id>/", views.get_course_progress),
    path("courses/<uuid:course_id>/progress/", views.get_course_progress),
]
