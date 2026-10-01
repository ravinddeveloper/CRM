from math import ceil

from django.http import Http404
from rest_framework import generics, permissions
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.courses.models import Category, Course, CourseStatus
from apps.courses.serializers import (
    CategorySerializer,
    CourseCatalogRecordSerializer,
    CourseDetailSerializer,
)
from infrastructure.database.factory import get_course_catalog_repository


class StandardResultsPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


class CourseListAPIView(generics.ListAPIView):
    """
    List published courses with filtering by category, difficulty, search query, and pagination.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = CourseCatalogRecordSerializer
    pagination_class = StandardResultsPagination

    def list(self, request, *args, **kwargs):
        paginator = self.paginator
        page_size = paginator.get_page_size(request) or paginator.page_size
        page_number = request.query_params.get(paginator.page_query_param, 1)
        if page_number in paginator.last_page_strings:
            requested_page = None
        else:
            try:
                requested_page = int(page_number)
                if requested_page < 1:
                    raise ValueError
            except (TypeError, ValueError) as exc:
                raise NotFound("Invalid page.") from exc

        free_param = request.query_params.get("is_free")
        is_free = free_param.lower() in ("true", "1") if free_param is not None else None
        repository = get_course_catalog_repository()
        filters = {
            "category": request.query_params.get("category") or None,
            "search": (request.query_params.get("search") or request.query_params.get("q") or "").strip(),
            "difficulty": request.query_params.get("difficulty") or None,
            "is_free": is_free,
        }
        count, records = repository.list_published(
            **filters, limit=1 if requested_page is None else page_size,
            offset=0 if requested_page is None else (requested_page - 1) * page_size,
        )
        last_page = max(ceil(count / page_size), 1)
        page = last_page if requested_page is None else min(requested_page, last_page)
        if requested_page is None or page != requested_page:
            _, records = repository.list_published(**filters, limit=page_size, offset=(page - 1) * page_size)

        def page_link(number):
            if number < 1 or number > last_page:
                return None
            params = request.query_params.copy()
            params[paginator.page_query_param] = number
            return request.build_absolute_uri(f"{request.path}?{params.urlencode()}")

        serializer = self.get_serializer(records, many=True)
        return Response({
            "count": count,
            "next": page_link(page + 1),
            "previous": page_link(page - 1),
            "results": serializer.data,
        })


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
