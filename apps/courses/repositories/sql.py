"""SQL adapter for the published course list API."""
from django.db import DatabaseError
from django.db.models import Q

from apps.courses.models import Course, CourseStatus
from infrastructure.database.exceptions import DatabaseConnectionError


class SQLCourseCatalogRepository:
    @staticmethod
    def _record(course):
        category = course.category
        effective_price = 0 if course.is_free else (
            course.discount_price if course.discount_price is not None else course.price
        )
        return {
            "id": str(course.pk), "title": course.title, "slug": course.slug,
            "short_description": course.short_description,
            "thumbnail": course.thumbnail.name if course.thumbnail else None,
            "category": ({"id": str(category.pk), "name": category.name, "slug": category.slug,
                          "description": category.description, "icon": category.icon} if category else None),
            "teacher_name": course.teacher.full_name, "price": course.price,
            "discount_price": course.discount_price, "effective_price": effective_price,
            "currency": course.currency, "is_free": course.is_free, "status": course.status,
            "is_featured": course.is_featured, "difficulty": course.difficulty,
            "estimated_duration": course.estimated_duration, "created_at": course.created_at,
        }

    def list_published(self, *, category=None, search="", difficulty=None, is_free=None, limit=20, offset=0):
        try:
            rows = Course.objects.filter(status=CourseStatus.PUBLISHED).select_related(
                "category", "teacher"
            )
            if category:
                rows = rows.filter(category__slug=category)
            if search:
                rows = rows.filter(
                    Q(title__icontains=search) | Q(short_description__icontains=search)
                    | Q(description__icontains=search)
                )
            if difficulty:
                rows = rows.filter(difficulty=difficulty)
            if is_free is not None:
                rows = rows.filter(is_free=is_free)
            count = rows.count()
            records = [self._record(row) for row in rows.order_by("-created_at", "-id")[offset:offset + limit]]
            return count, records
        except DatabaseError as exc:
            raise DatabaseConnectionError("The SQL database could not list published courses.") from exc
