"""Progress API URL patterns."""
from django.urls import path

from . import views

app_name = "progress_api"

urlpatterns = [
    # Video progress - called by player every N seconds
    path(
        "lectures/<uuid:lecture_id>/position/",
        views.update_video_position,
        name="update_position",
    ),
    # Resume - called when student opens a lecture
    path(
        "lectures/<uuid:lecture_id>/resume/",
        views.get_resume_position,
        name="get_resume_position",
    ),
    # Manual completion (text/resource lectures)
    path(
        "lectures/<uuid:lecture_id>/complete/",
        views.mark_lecture_complete,
        name="mark_complete",
    ),
    # Course-level progress for dashboard
    path(
        "courses/<uuid:course_id>/progress/",
        views.get_course_progress,
        name="course_progress",
    ),
]
