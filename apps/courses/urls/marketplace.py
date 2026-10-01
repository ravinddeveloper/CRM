"""Courses marketplace URLs."""
from django.urls import path

from apps.courses import marketplace_views as views

app_name = "marketplace"

urlpatterns = [
    path("", views.course_list_view, name="course_list"),
    path("courses/", views.course_list_view, name="courses"),
    path("courses/<slug:slug>/", views.course_detail_view, name="course_detail"),
    path("categories/", views.category_list_view, name="categories"),
    path("categories/", views.category_list_view, name="category_list"),
    path("categories/<slug:slug>/", views.category_detail_view, name="category_detail"),
    path("search/", views.search_view, name="search"),
]
