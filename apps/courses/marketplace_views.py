"""Marketplace views - public course browsing."""
import logging
from decimal import Decimal, InvalidOperation
from math import ceil
from types import SimpleNamespace

from django.core.files.storage import default_storage
from django.core.paginator import Page, Paginator
from django.shortcuts import render

from apps.analytics.services import AnalyticsService
from infrastructure.database.factory import get_course_catalog_repository

logger = logging.getLogger("apps.courses")


class CatalogPaginator(Paginator):
    """Paginator metadata for a repository page already fetched with limit/offset."""
    def __init__(self, count, per_page):
        super().__init__([], per_page)
        self._catalog_count = count

    @property
    def count(self):
        return self._catalog_count

    @property
    def num_pages(self):
        return max(ceil(self.count / self.per_page), 1)


def _catalog_cards(records):
    for record in records:
        path = record.get("thumbnail")
        record["thumbnail_url"] = default_storage.url(path) if path else ""
    return records


def _catalog_page(repository, filters, raw_page, page_size):
    is_last = raw_page == "last"
    try:
        page_number = None if is_last else max(int(raw_page), 1)
    except (TypeError, ValueError):
        page_number = 1
    count, records = repository.list_published(
        **filters, limit=1 if is_last else page_size,
        offset=0 if is_last else (page_number - 1) * page_size,
    )
    paginator = CatalogPaginator(count, page_size)
    resolved_page = paginator.num_pages if is_last else min(page_number, paginator.num_pages)
    if is_last or resolved_page != page_number:
        _, records = repository.list_published(
            **filters, limit=page_size, offset=(resolved_page - 1) * page_size
        )
    page_obj = Page(_catalog_cards(records), resolved_page, paginator)
    return paginator, page_obj


def course_list_view(request):
    """Main course marketplace page with filtering and search."""
    category_slug = request.GET.get("category")
    difficulty = request.GET.get("difficulty")
    price_min = request.GET.get("price_min")
    price_max = request.GET.get("price_max")
    q = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "-created_at")
    sort = sort if sort in {"newest", "popular", "rating", "price_low", "price_high"} else "newest"
    def valid_price(value):
        if not value:
            return None
        try:
            amount = Decimal(value)
            return str(amount) if amount.is_finite() else None
        except (InvalidOperation, TypeError, ValueError):
            return None

    repository = get_course_catalog_repository()
    filters = {
        "category": category_slug or None, "search": q, "difficulty": difficulty or None,
        "is_free": None, "price_min": valid_price(price_min), "price_max": valid_price(price_max),
        "sort": sort, "include_related_search": True,
    }
    paginator, page_obj = _catalog_page(repository, filters, request.GET.get("page", "1"), 12)
    courses = page_obj.object_list

    # Sidebar data
    categories = [
        SimpleNamespace(**category)
        for category in repository.list_categories(root_only=True)
    ]
    _, featured_courses = repository.list_published(
        category=None, search="", difficulty=None, is_free=None, featured_only=True,
        sort="newest", limit=4, offset=0,
    )
    featured_courses = _catalog_cards(featured_courses)

    from apps.notifications.models import Announcement
    latest_announcements = Announcement.objects.filter(
        is_published=True, course__isnull=True
    ).order_by("-is_pinned", "-created_at")[:4]

    total_count = paginator.count
    if total_count == 0 and courses:
        total_count = len(courses)

    context = {
        "page_obj": page_obj,
        "courses": page_obj.object_list,
        "categories": categories,
        "featured_courses": featured_courses,
        "latest_announcements": latest_announcements,
        "q": q,
        "selected_category": category_slug,
        "selected_difficulty": difficulty,
        "price_min": price_min,
        "price_max": price_max,
        "sort": sort,
        "total_count": total_count,
        "title": f"Courses{' — ' + q if q else ''}",
        "meta_description": "Browse our collection of expert-led online courses.",
    }
    return render(request, "marketplace/course_list.html", context)


def course_detail_view(request, slug):
    """Course detail page - public with role-specific mentor and admin controls."""
    user = request.user
    is_authenticated = user.is_authenticated
    repository = get_course_catalog_repository()
    course = repository.get_by_slug(slug)
    if course is None:
        from django.http import Http404
        raise Http404("Course not found.")

    is_admin = bool(is_authenticated and (user.is_admin or user.is_staff))
    is_course_mentor = bool(
        is_authenticated and user.is_teacher and str(user.id) == course.get("teacher_id")
    )
    can_preview_unpublished = is_admin or is_course_mentor
    if course.get("status") != "published" and not can_preview_unpublished:
        from django.http import Http404
        raise Http404("Course not found.")
    course["thumbnail_url"] = default_storage.url(course["thumbnail"]) if course.get("thumbnail") else ""

    # Track view
    if not request.session.get(f"viewed_course_{course['id']}"):
        AnalyticsService.record_course_view(
            course_id=course["id"],
            user_id=user.id if is_authenticated else None,
            ip_address=request.META.get("REMOTE_ADDR"),
            session_key=request.session.session_key or "",
        )
        request.session[f"viewed_course_{course['id']}"] = True

    # Identify user roles
    is_other_teacher = bool(is_authenticated and user.is_teacher and not is_course_mentor)
    is_enrolled = False
    enrollment = None
    course_progress = None

    if is_authenticated:
        # For student learners (not course creator and not admin): check enrollment
        if not is_course_mentor and not is_admin:
            from apps.enrollments.models import Enrollment
            enrollment = Enrollment.objects.filter(
                user=user, course_id=course["id"], status="active"
            ).select_related("progress").first()
            if enrollment:
                is_enrolled = True
                course_progress = getattr(enrollment, "progress", None)

    sections = course.get("sections", [])
    # Defensive guard: if the repository ever returns ORM Section objects instead
    # of plain dicts (e.g. from a legacy code path or a direct queryset), serialize
    # them now so the template always receives plain Python dicts with a "lectures" list.
    _normalized = []
    for sec in sections:
        if isinstance(sec, dict):
            _normalized.append(sec)
        else:
            # ORM Section object — serialize defensively
            lectures = [
                {
                    "id": str(lec.pk), "title": lec.title, "order": lec.order,
                    "estimated_duration": lec.estimated_duration,
                    "duration_seconds": lec.estimated_duration,
                    "is_free_preview": getattr(lec, "is_free_preview", False),
                    "is_published": lec.is_published,
                }
                for lec in sec.lectures.all().order_by("order")
            ]
            _normalized.append({
                "id": str(sec.pk), "title": sec.title, "order": sec.order,
                "is_published": sec.is_published,
                "lecture_count": len(lectures),
                "lectures": lectures,
            })
    sections = _normalized

    if not (is_course_mentor or is_admin):
        sections = [s for s in sections if s.get("is_published", True)]
    for section in sections:
        section["lecture_count"] = len(section.get("lectures", []))


    context = {
        "course": course,
        "is_admin": is_admin,
        "is_course_mentor": is_course_mentor,
        "is_other_teacher": is_other_teacher,
        "is_enrolled": is_enrolled,
        "enrollment": enrollment,
        "course_progress": course_progress,
        "sections": sections,
        "title": f"{course['title']} — {course['teacher']['full_name']}",
        "meta_description": course.get("short_description", ""),
        "og_image": course["thumbnail_url"],
    }
    return render(request, "marketplace/course_detail.html", context)


def category_list_view(request):
    categories = [
        SimpleNamespace(**category)
        for category in get_course_catalog_repository().list_categories(root_only=True)
    ]
    return render(request, "marketplace/category_list.html", {"categories": categories})


def category_detail_view(request, slug):
    category = get_course_catalog_repository().get_category_by_slug(slug)
    if category is None:
        from django.http import Http404
        raise Http404("Category not found.")
    category = SimpleNamespace(**category)
    repository = get_course_catalog_repository()
    paginator, page_obj = _catalog_page(repository, {
        "category": category.slug, "search": "", "difficulty": None, "is_free": None,
        "sort": "newest",
    }, request.GET.get("page", "1"), 12)
    courses = page_obj.object_list
    return render(request, "marketplace/category_detail.html", {
        "category": category,
        "page_obj": page_obj,
        "courses": courses,
    })


def search_view(request):
    q = request.GET.get("q", "").strip()
    courses = []
    if q:
        _, courses = get_course_catalog_repository().list_published(
            category=None, search=q, difficulty=None, is_free=None,
            include_related_search=True, limit=20, offset=0,
        )
        courses = _catalog_cards(courses)
    if request.htmx:
        return render(request, "marketplace/_search_results.html", {"courses": courses, "q": q})
    return render(request, "marketplace/search.html", {"courses": courses, "q": q})
