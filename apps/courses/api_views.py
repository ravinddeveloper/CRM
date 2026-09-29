from django.db.models import Q
from django.http import Http404
from rest_framework import generics, permissions
from rest_framework.pagination import PageNumberPagination

from apps.courses.models import Category, Course, CourseStatus
from apps.courses.serializers import (
    CategorySerializer,
    CourseDetailSerializer,
    CourseListSerializer,
)


class StandardResultsPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


class CourseListAPIView(generics.ListAPIView):
    """
    List published courses with filtering by category, difficulty, search query, and pagination.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = CourseListSerializer
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        queryset = (
            Course.objects.filter(status=CourseStatus.PUBLISHED)
            .select_related("category", "teacher")
            .prefetch_related("tags")
            .order_by("-created_at")
        )

        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category__slug=category)

        search = self.request.query_params.get("search") or self.request.query_params.get("q")
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(short_description__icontains=search) |
                Q(description__icontains=search)
            )

        difficulty = self.request.query_params.get("difficulty")
        if difficulty:
            queryset = queryset.filter(difficulty=difficulty)

        is_free = self.request.query_params.get("is_free")
        if is_free is not None:
            queryset = queryset.filter(is_free=(is_free.lower() in ["true", "1"]))

        return queryset


class CourseDetailAPIView(generics.RetrieveAPIView):
    """
    Retrieve single course by UUID.
    Draft courses return 404 for students / guests.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = CourseDetailSerializer
    queryset = Course.objects.all().select_related("category", "teacher", "teacher__profile")
    lookup_field = "id"

    def get_object(self):
        course = super().get_object()
        if course.status != CourseStatus.PUBLISHED:
            user = self.request.user
            if not user.is_authenticated or (not user.is_staff and course.teacher != user):
                raise Http404("Course not found or not published.")
        return course


class CategoryListAPIView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = CategorySerializer
    queryset = Category.objects.filter(is_active=True).order_by("order", "name")
