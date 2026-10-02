"""SQL adapter for the published course list API."""
from django.db import DatabaseError
from django.db.models import Q
from django.core.exceptions import ObjectDoesNotExist

from apps.courses.models import Category, Course, CourseStatus
from infrastructure.database.exceptions import DatabaseConnectionError


class SQLCourseCatalogRepository:
    @staticmethod
    def _category_record(category):
        return {
            "id": str(category.pk), "name": category.name, "slug": category.slug,
            "description": category.description, "icon": category.icon,
            "image": category.image.name if category.image else None,
            "is_active": category.is_active, "order": category.order,
            "parent_id": str(category.parent_id) if category.parent_id else None,
        }

    def list_categories(self, *, root_only=False):
        rows = Category.objects.filter(is_active=True).select_related("parent").order_by("order", "name")
        if root_only:
            rows = rows.filter(parent__isnull=True)
        return [self._category_record(row) for row in rows]

    def get_category_by_slug(self, slug):
        category = Category.objects.filter(slug=slug, is_active=True).first()
        return self._category_record(category) if category else None

    @staticmethod
    def _lecture_record(lecture):
        """Serialize a Lecture ORM object to a plain dict for the catalog."""
        return {
            "id": str(lecture.pk),
            "title": lecture.title,
            "order": lecture.order,
            "estimated_duration": lecture.estimated_duration,
            "duration_seconds": lecture.estimated_duration,
            "is_free_preview": lecture.is_free_preview,
            "is_published": lecture.is_published,
        }

    @staticmethod
    def _section_record(section):
        """Serialize a Section ORM object (with prefetched lectures) to a plain dict."""
        lectures = [
            SQLCourseCatalogRepository._lecture_record(lec)
            for lec in section.lectures.all()
        ]
        return {
            "id": str(section.pk),
            "title": section.title,
            "order": section.order,
            "is_published": section.is_published,
            "lecture_count": len(lectures),
            "lectures": lectures,
        }

    @staticmethod
    def _record(course):
        category = course.category
        effective_price = 0 if course.is_free else (
            course.discount_price if course.discount_price is not None else course.price
        )
        return {
            "id": str(course.pk), "title": course.title, "slug": course.slug,
            "short_description": course.short_description,
            "description": course.description,
            "thumbnail": course.thumbnail.name if course.thumbnail else None,
            "category": ({"id": str(category.pk), "name": category.name, "slug": category.slug,
                          "description": category.description, "icon": category.icon} if category else None),
            "teacher_name": course.teacher.full_name, "price": course.price,
            "teacher_first_name": course.teacher.first_name, "teacher_email": course.teacher.email,
            "teacher_last_name": course.teacher.last_name,
            "discount_price": course.discount_price, "effective_price": effective_price,
            "currency": course.currency, "is_free": course.is_free, "status": course.status,
            "is_featured": course.is_featured, "difficulty": course.difficulty,
            "estimated_duration": course.estimated_duration, "created_at": course.created_at,
            "enrollment_count": course.enrollment_count, "average_rating": course.average_rating,
        }

    def list_published(self, *, category=None, search="", difficulty=None, is_free=None,
                       price_min=None, price_max=None, sort="newest", featured_only=False,
                       include_related_search=False,
                       limit=20, offset=0):
        try:
            rows = Course.objects.filter(status=CourseStatus.PUBLISHED).select_related(
                "category", "teacher"
            )
            if category:
                rows = rows.filter(category__slug=category)
            if search:
                search_filter = (
                    Q(title__icontains=search) | Q(short_description__icontains=search)
                    | Q(description__icontains=search)
                )
                if include_related_search:
                    search_filter |= (
                        Q(teacher__first_name__icontains=search)
                        | Q(teacher__last_name__icontains=search)
                        | Q(tags__name__icontains=search)
                    )
                rows = rows.filter(search_filter)
                if include_related_search:
                    rows = rows.distinct()
            if difficulty:
                rows = rows.filter(difficulty=difficulty)
            if is_free is not None:
                rows = rows.filter(is_free=is_free)
            if price_min:
                rows = rows.filter(price__gte=price_min)
            if price_max:
                rows = rows.filter(price__lte=price_max)
            if featured_only:
                rows = rows.filter(is_featured=True)
            sort_options = {
                "newest": ("-created_at", "-id"), "popular": ("-enrollment_count", "-id"),
                "rating": ("-average_rating", "-id"), "price_low": ("price", "id"),
                "price_high": ("-price", "-id"),
            }
            count = rows.count()
            records = [self._record(row) for row in rows.order_by(*sort_options.get(sort, sort_options["newest"]))[offset:offset + limit]]
            return count, records
        except DatabaseError as exc:
            raise DatabaseConnectionError("The SQL database could not list published courses.") from exc

    def get_by_id(self, course_id):
        try:
            course = Course.objects.select_related(
                "category", "teacher", "teacher__profile"
            ).prefetch_related(
                "tags", "sections", "sections__lectures"
            ).filter(pk=course_id).first()
            if course is None:
                return None
            record = self._record(course)
            try:
                teacher_bio = course.teacher.profile.bio
            except ObjectDoesNotExist:
                teacher_bio = ""
            # Serialize sections + lectures eagerly to plain dicts so the
            # template never receives ORM objects or RelatedManagers.
            sections = [
                self._section_record(section)
                for section in course.sections.all().order_by("order")
            ]
            record.update({
                "teacher_id": str(course.teacher_id),
                "teacher": {
                    "full_name": course.teacher.full_name,
                    "first_name": course.teacher.first_name,
                    "email": course.teacher.email,
                    "profile": {"bio": teacher_bio},
                },
                "is_published": course.is_published,
                "discount_percentage": course.discount_percentage,
                "total_lectures_count": sum(s["lecture_count"] for s in sections),
                "description": course.description,
                "preview_video_key": course.preview_video_key,
                "language": course.language,
                "learning_objectives": list(course.learning_objectives) if course.learning_objectives else [],
                "requirements": list(course.requirements) if course.requirements else [],
                "updated_at": course.updated_at,
                "tags": [{"id": str(tag.pk), "name": tag.name, "slug": tag.slug} for tag in course.tags.all()],
                "sections": sections,
            })
            return record
        except DatabaseError as exc:
            raise DatabaseConnectionError("The SQL database could not retrieve the course catalog record.") from exc

    def get_by_slug(self, slug):
        try:
            course_id = Course.objects.filter(slug=slug).values_list("pk", flat=True).first()
            return self.get_by_id(course_id) if course_id is not None else None
        except DatabaseError as exc:
            raise DatabaseConnectionError("The SQL database could not retrieve the course catalog record.") from exc
