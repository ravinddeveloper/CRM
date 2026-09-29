from django.urls import path

from apps.courses.api_views import (
    CategoryListAPIView,
    CourseDetailAPIView,
    CourseListAPIView,
)

app_name = "courses_api"

urlpatterns = [
    path("", CourseListAPIView.as_view(), name="course_list"),
    path("<uuid:id>/", CourseDetailAPIView.as_view(), name="course_detail"),
    path("categories/", CategoryListAPIView.as_view(), name="category_list"),
]
