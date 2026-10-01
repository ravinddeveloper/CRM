"""Marketplace views - public course browsing."""
import logging

from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from apps.analytics.services import AnalyticsService
from apps.courses.models import Category, Course, CourseStatus

logger = logging.getLogger("apps.courses")


def course_list_view(request):
    """Main course marketplace page with filtering and search."""
    courses = Course.objects.filter(status=CourseStatus.PUBLISHED).select_related(
        "teacher", "category"
    ).prefetch_related("tags")

    # Filters
    category_slug = request.GET.get("category")
    if category_slug:
        courses = courses.filter(category__slug=category_slug)

    difficulty = request.GET.get("difficulty")
    if difficulty:
        courses = courses.filter(difficulty=difficulty)

    price_min = request.GET.get("price_min")
    price_max = request.GET.get("price_max")
    if price_min:
        courses = courses.filter(price__gte=price_min)
    if price_max:
        courses = courses.filter(price__lte=price_max)

    # Search
    q = request.GET.get("q", "").strip()
    if q:
        courses = courses.filter(
            Q(title__icontains=q)
            | Q(short_description__icontains=q)
            | Q(description__icontains=q)
            | Q(teacher__first_name__icontains=q)
            | Q(teacher__last_name__icontains=q)
            | Q(tags__name__icontains=q)
        ).distinct()

    # Sorting
    sort = request.GET.get("sort", "-created_at")
    sort_options = {
        "newest": "-created_at",
        "popular": "-enrollment_count",
        "rating": "-average_rating",
        "price_low": "price",
        "price_high": "-price",
    }
    sort_field = sort_options.get(sort, "-created_at")
    courses = courses.order_by(sort_field)

    # Pagination
    paginator = Paginator(courses, 12)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    # Sidebar data
    categories = Category.objects.filter(is_active=True, parent__isnull=True)
    featured_courses = Course.objects.filter(
        status=CourseStatus.PUBLISHED, is_featured=True
    ).select_related("teacher")[:4]

    context = {
        "page_obj": page_obj,
        "courses": page_obj.object_list,
        "categories": categories,
        "featured_courses": featured_courses,
        "q": q,
        "selected_category": category_slug,
        "selected_difficulty": difficulty,
        "sort": sort,
        "total_count": paginator.count,
        "title": f"Courses{' — ' + q if q else ''}",
        "meta_description": "Browse our collection of expert-led online courses.",
    }
    return render(request, "marketplace/course_list.html", context)


def course_detail_view(request, slug):
    """Course detail page - public with role-specific mentor and admin controls."""
    user = request.user
    is_authenticated = user.is_authenticated

    # Allow mentors and admins to preview their unpublished/draft courses
    if is_authenticated and (user.is_admin or user.is_staff or (user.is_teacher and Course.objects.filter(slug=slug, teacher=user).exists())):
        course = get_object_or_404(
            Course.objects.select_related("teacher", "category", "teacher__profile")
            .prefetch_related(
                "sections__lectures",
                "tags",
                "reviews__user",
            ),
            slug=slug,
        )
    else:
        course = get_object_or_404(
            Course.objects.select_related("teacher", "category", "teacher__profile")
            .prefetch_related(
                "sections__lectures",
                "tags",
                "reviews__user",
            ),
            slug=slug,
            status=CourseStatus.PUBLISHED,
        )

    # Track view
    if not request.session.get(f"viewed_course_{course.id}"):
        AnalyticsService.record_course_view(
            course_id=course.id,
            user_id=user.id if is_authenticated else None,
            ip_address=request.META.get("REMOTE_ADDR"),
            session_key=request.session.session_key or "",
        )
        course.total_views += 1
        course.save(update_fields=["total_views"])
        request.session[f"viewed_course_{course.id}"] = True

    # Identify user roles
    is_admin = False
    is_course_mentor = False
    is_other_teacher = False
    is_enrolled = False
    enrollment = None
    course_progress = None

    if is_authenticated:
        is_admin = bool(user.is_admin or user.is_staff)
        is_course_mentor = bool(user.is_teacher and course.teacher_id == user.id)
        is_other_teacher = bool(user.is_teacher and not is_course_mentor)

        # For student learners (not course creator and not admin): check enrollment
        if not is_course_mentor and not is_admin:
            from apps.enrollments.models import Enrollment
            enrollment = Enrollment.objects.filter(
                user=user, course=course, status="active"
            ).select_related("progress").first()
            if enrollment:
                is_enrolled = True
                course_progress = getattr(enrollment, "progress", None)

    # Reviews
    reviews = course.reviews.filter(is_approved=True, is_hidden=False).select_related("user")[:10]

    # Sections to display
    if is_course_mentor or is_admin:
        sections = course.sections.prefetch_related("lectures").order_by("order")
    else:
        sections = course.sections.filter(is_published=True).prefetch_related("lectures").order_by("order")

    context = {
        "course": course,
        "is_admin": is_admin,
        "is_course_mentor": is_course_mentor,
        "is_other_teacher": is_other_teacher,
        "is_enrolled": is_enrolled,
        "enrollment": enrollment,
        "course_progress": course_progress,
        "reviews": reviews,
        "sections": sections,
        "title": f"{course.title} — {course.teacher.full_name}",
        "meta_description": course.short_description,
        "og_image": course.thumbnail.url if course.thumbnail else "",
    }
    return render(request, "marketplace/course_detail.html", context)


def category_list_view(request):
    categories = Category.objects.filter(is_active=True, parent__isnull=True).prefetch_related("subcategories")
    return render(request, "marketplace/category_list.html", {"categories": categories})


def category_detail_view(request, slug):
    category = get_object_or_404(Category, slug=slug, is_active=True)
    courses = Course.objects.filter(
        category=category, status=CourseStatus.PUBLISHED
    ).select_related("teacher")
    paginator = Paginator(courses, 12)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    return render(request, "marketplace/category_detail.html", {
        "category": category,
        "page_obj": page_obj,
        "courses": page_obj.object_list,
    })


def search_view(request):
    q = request.GET.get("q", "").strip()
    courses = []
    if q:
        courses = Course.objects.filter(
            status=CourseStatus.PUBLISHED
        ).filter(
            Q(title__icontains=q)
            | Q(short_description__icontains=q)
        ).select_related("teacher")[:20]
    if request.htmx:
        return render(request, "marketplace/_search_results.html", {"courses": courses, "q": q})
    return render(request, "marketplace/search.html", {"courses": courses, "q": q})
