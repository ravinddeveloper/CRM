"""
Shared test fixtures and factories for the LMS test suite.
"""
import uuid
from decimal import Decimal
from django.contrib.auth import get_user_model

User = get_user_model()


def make_user(email=None, role="student", password="TestPass123!", **kwargs):
    """Create and return a user for testing."""
    email = email or f"{uuid.uuid4().hex[:8]}@test.com"
    user = User.objects.create_user(
        email=email,
        password=password,
        username=email.split("@")[0],
        role=role,
        email_verified=True,
        **kwargs,
    )
    return user


def make_admin(**kwargs):
    return make_user(role="admin", is_staff=True, is_superuser=True, **kwargs)


def make_teacher(**kwargs):
    return make_user(role="teacher", **kwargs)


def make_student(**kwargs):
    return make_user(role="student", **kwargs)


def make_category(name=None):
    from apps.courses.models import Category
    name = name or f"Category {uuid.uuid4().hex[:6]}"
    return Category.objects.create(name=name)


def make_course(teacher=None, price=Decimal("999.00"), status="published", **kwargs):
    from apps.courses.models import Course
    teacher = teacher or make_teacher()
    return Course.objects.create(
        title=kwargs.pop("title", f"Test Course {uuid.uuid4().hex[:6]}"),
        short_description="A test course.",
        description="A longer test course description.",
        teacher=teacher,
        price=price,
        status=status,
        **kwargs,
    )


def make_section(course=None, order=1):
    from apps.courses.models import Section
    course = course or make_course()
    return Section.objects.create(
        course=course,
        title=f"Section {order}",
        order=order,
    )


def make_lecture(section=None, is_published=True, is_free_preview=False, with_video=True):
    from apps.lectures.models import Lecture, LectureVideo
    section = section or make_section()
    lecture = Lecture.objects.create(
        section=section,
        title=f"Lecture {uuid.uuid4().hex[:6]}",
        order=1,
        is_published=is_published,
        is_free_preview=is_free_preview,
        estimated_duration=600,
    )
    if with_video:
        LectureVideo.objects.create(
            lecture=lecture,
            storage_key=f"videos/{lecture.id}.mp4",
            duration_seconds=600,
        )
    return lecture


def make_order(user=None, course=None, status="completed"):
    from apps.orders.models import Order, OrderItem, OrderStatus
    user = user or make_student()
    course = course or make_course()
    order = Order.objects.create(
        user=user,
        currency="INR",
        subtotal=course.effective_price,
        total=course.effective_price,
        status=status,
        payment_provider="razorpay",
    )
    OrderItem.objects.create(
        order=order,
        course=course,
        unit_price=course.effective_price,
        final_price=course.effective_price,
    )
    return order


def make_enrollment(user=None, course=None, order=None):
    from apps.enrollments.models import Enrollment, EnrollmentStatus
    from apps.progress.models import CourseProgress
    user = user or make_student()
    course = course or make_course()
    enrollment = Enrollment.objects.create(
        user=user,
        course=course,
        order=order,
        status=EnrollmentStatus.ACTIVE,
        access_type="lifetime",
    )
    CourseProgress.objects.create(enrollment=enrollment)
    return enrollment
