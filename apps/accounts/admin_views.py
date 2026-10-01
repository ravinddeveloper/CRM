"""Admin panel views - complete platform management console."""
import logging
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, ProtectedError, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_http_methods

from apps.audit.models import AuditAction, AuditLog
from apps.coupons.models import Coupon, DiscountType
from apps.courses.models import Category, Course, CourseStatus, DifficultyLevel, Section
from apps.enrollments.models import AccessType, Enrollment, EnrollmentStatus
from apps.lectures.models import Attachment, Lecture, LectureNote, LectureVideo, NoteType
from apps.orders.models import Order, OrderStatus
from apps.payments.models import Payment, PaymentStatus

from .services import AccountService

User = get_user_model()
logger = logging.getLogger("apps.accounts")


def admin_required(view_func):
    """Decorator requiring admin role."""
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_admin:
            from apps.common.views import error_403
            return error_403(request)
        return view_func(request, *args, **kwargs)
    return wrapper


# ─────────────────────────────────────────────────────────────────────────────
# 1. OVERVIEW & ANALYTICS
# ─────────────────────────────────────────────────────────────────────────────

@admin_required
def dashboard_view(request):
    """Admin dashboard with high-level operational metrics and quick actions."""
    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)

    total_rev = Order.objects.filter(status=OrderStatus.COMPLETED).aggregate(total=Sum("total"))["total"] or Decimal("0.00")
    rev_30d = Order.objects.filter(
        created_at__gte=thirty_days_ago, status=OrderStatus.COMPLETED
    ).aggregate(total=Sum("total"))["total"] or Decimal("0.00")

    stats = {
        "total_users": User.objects.count(),
        "total_students": User.objects.filter(role="student").count(),
        "total_teachers": User.objects.filter(role="teacher").count(),
        "total_courses": Course.objects.count(),
        "published_courses": Course.objects.filter(status=CourseStatus.PUBLISHED).count(),
        "draft_courses": Course.objects.filter(status=CourseStatus.DRAFT).count(),
        "total_orders": Order.objects.count(),
        "successful_orders": Order.objects.filter(status=OrderStatus.COMPLETED).count(),
        "total_revenue": total_rev,
        "revenue_30d": rev_30d,
        "active_enrollments": Enrollment.objects.filter(status=EnrollmentStatus.ACTIVE).count(),
        "total_coupons": Coupon.objects.count(),
        "new_users_30d": User.objects.filter(date_joined__gte=thirty_days_ago).count(),
        "new_orders_30d": Order.objects.filter(
            created_at__gte=thirty_days_ago, status=OrderStatus.COMPLETED
        ).count(),
    }

    recent_orders = Order.objects.select_related("user").order_by("-created_at")[:8]
    recent_users = User.objects.order_by("-date_joined")[:8]
    recent_courses = Course.objects.select_related("teacher", "category").order_by("-created_at")[:6]

    context = {
        "active_tab": "overview",
        "stats": stats,
        "recent_orders": recent_orders,
        "recent_users": recent_users,
        "recent_courses": recent_courses,
    }
    return render(request, "dashboard/admin/index.html", context)


# ─────────────────────────────────────────────────────────────────────────────
# 2. COURSE MANAGEMENT (ADD, EDIT, CURRICULUM, PUBLISH, DELETE)
# ─────────────────────────────────────────────────────────────────────────────

@admin_required
def course_list_view(request):
    """List all platform courses with search, filters, and management controls."""
    qs = Course.objects.select_related("category", "teacher").annotate(
        student_count=Count("enrollments", filter=Q(enrollments__status=EnrollmentStatus.ACTIVE)),
        section_count=Count("sections", distinct=True),
    ).order_by("-created_at")

    # Search filter
    search = request.GET.get("q", "").strip()
    if search:
        qs = qs.filter(
            Q(title__icontains=search)
            | Q(short_description__icontains=search)
            | Q(teacher__email__icontains=search)
            | Q(teacher__first_name__icontains=search)
            | Q(teacher__last_name__icontains=search)
        )

    # Status filter
    status = request.GET.get("status", "").strip()
    if status in CourseStatus.values:
        qs = qs.filter(status=status)

    context = {
        "active_tab": "courses",
        "courses": qs,
        "search_query": search,
        "selected_status": status,
        "total_count": Course.objects.count(),
        "published_count": Course.objects.filter(status=CourseStatus.PUBLISHED).count(),
        "draft_count": Course.objects.filter(status=CourseStatus.DRAFT).count(),
        "archived_count": Course.objects.filter(status=CourseStatus.ARCHIVED).count(),
    }
    return render(request, "dashboard/admin/courses/list.html", context)


@admin_required
@require_http_methods(["GET", "POST"])
def course_create_view(request):
    """Admin interface to create a new course."""
    categories = Category.objects.filter(is_active=True).order_by("name")
    teachers = User.objects.filter(role__in=["teacher", "admin"]).order_by("email")

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        short_description = request.POST.get("short_description", "").strip()
        description = request.POST.get("description", "").strip()
        category_id = request.POST.get("category_id")
        teacher_id = request.POST.get("teacher_id")
        difficulty = request.POST.get("difficulty", DifficultyLevel.BEGINNER)
        price_raw = request.POST.get("price", "0.00").strip()
        discount_price_raw = request.POST.get("discount_price", "").strip()
        is_free = request.POST.get("is_free") == "on"
        status = request.POST.get("status", CourseStatus.DRAFT)
        language = request.POST.get("language", "English").strip()

        errors = []
        if not title:
            errors.append("Course title is required.")
        if not short_description:
            errors.append("Short description is required.")
        if not description:
            errors.append("Full description is required.")

        try:
            price = Decimal(price_raw) if price_raw else Decimal("0.00")
            if price < 0:
                errors.append("Price cannot be negative.")
        except Exception:
            errors.append("Invalid price format.")
            price = Decimal("0.00")

        discount_price = None
        if discount_price_raw:
            try:
                discount_price = Decimal(discount_price_raw)
                if discount_price < 0 or discount_price >= price:
                    errors.append("Discount price must be less than the regular price.")
            except Exception:
                errors.append("Invalid discount price.")

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(request, "dashboard/admin/courses/form.html", {
                "active_tab": "courses",
                "categories": categories,
                "teachers": teachers,
                "is_create": True,
                "form_data": request.POST,
            })

        # Resolve teacher
        teacher = User.objects.filter(id=teacher_id).first() if teacher_id else request.user
        category = Category.objects.filter(id=category_id).first() if category_id else None

        course = Course(
            title=title,
            short_description=short_description,
            description=description,
            category=category,
            teacher=teacher,
            difficulty=difficulty,
            price=price,
            discount_price=discount_price,
            is_free=is_free,
            status=status,
            language=language,
        )

        if "thumbnail" in request.FILES:
            course.thumbnail = request.FILES["thumbnail"]

        course.save()

        # Audit log
        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.COURSE_CREATED,
            object_type="Course",
            object_id=str(course.id),
            object_repr=course.title,
            changes={"price": str(course.price), "status": course.status},
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        messages.success(request, f"Course '{course.title}' created! Now add curriculum sections.")
        return redirect("admin_panel:course_curriculum", course_id=course.id)

    return render(request, "dashboard/admin/courses/form.html", {
        "active_tab": "courses",
        "categories": categories,
        "teachers": teachers,
        "is_create": True,
        "course": None,
        "form_data": {},
    })


@admin_required
@require_http_methods(["GET", "POST"])
def course_edit_view(request, course_id):
    """Admin interface to edit an existing course."""
    course = get_object_or_404(Course, id=course_id)
    categories = Category.objects.filter(is_active=True).order_by("name")
    teachers = User.objects.filter(role__in=["teacher", "admin"]).order_by("email")

    if request.method == "POST":
        course.title = request.POST.get("title", "").strip() or course.title
        course.short_description = request.POST.get("short_description", "").strip() or course.short_description
        course.description = request.POST.get("description", "").strip() or course.description

        category_id = request.POST.get("category_id")
        if category_id:
            course.category = Category.objects.filter(id=category_id).first()

        teacher_id = request.POST.get("teacher_id")
        if teacher_id:
            teacher = User.objects.filter(id=teacher_id).first()
            if teacher:
                course.teacher = teacher

        course.difficulty = request.POST.get("difficulty", course.difficulty)
        course.language = request.POST.get("language", course.language)
        course.is_free = request.POST.get("is_free") == "on"
        course.status = request.POST.get("status", course.status)

        price_raw = request.POST.get("price", "").strip()
        if price_raw:
            try:
                course.price = Decimal(price_raw)
            except Exception:
                pass

        disc_raw = request.POST.get("discount_price", "").strip()
        if disc_raw:
            try:
                course.discount_price = Decimal(disc_raw)
            except Exception:
                pass
        else:
            course.discount_price = None

        if "thumbnail" in request.FILES:
            course.thumbnail = request.FILES["thumbnail"]

        course.save()
        messages.success(request, f"Course '{course.title}' updated successfully.")
        return redirect("admin_panel:course_list")

    return render(request, "dashboard/admin/courses/form.html", {
        "active_tab": "courses",
        "course": course,
        "categories": categories,
        "teachers": teachers,
        "is_create": False,
    })


@admin_required
def course_curriculum_view(request, course_id):
    """Curriculum builder for admin - manage sections and lectures."""
    course = get_object_or_404(
        Course.objects.prefetch_related(
            "sections__lectures__video",
            "sections__lectures__notes",
        ),
        id=course_id,
    )
    sections = course.sections.all().order_by("order")

    context = {
        "active_tab": "courses",
        "course": course,
        "sections": sections,
    }
    return render(request, "dashboard/admin/courses/curriculum.html", context)


@admin_required
@require_http_methods(["POST"])
def course_publish_toggle_view(request, course_id):
    """Toggle a course's published/draft status."""
    course = get_object_or_404(Course, id=course_id)
    if course.is_published:
        course.unpublish()
        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.COURSE_UNPUBLISHED,
            object_type="Course",
            object_id=str(course.id),
            object_repr=course.title,
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        messages.info(request, f"'{course.title}' has been moved to Draft.")
    else:
        # Check if course has at least one section
        if not course.sections.exists():
            messages.error(request, "Cannot publish: Please add at least one module/section to this course.")
            return redirect("admin_panel:course_curriculum", course_id=course.id)

        course.publish()
        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.COURSE_PUBLISHED,
            object_type="Course",
            object_id=str(course.id),
            object_repr=course.title,
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        messages.success(request, f"'{course.title}' is now Published and live on the marketplace!")

    return redirect(request.META.get("HTTP_REFERER") or "admin_panel:course_list")


@admin_required
@require_http_methods(["POST"])
def course_delete_view(request, course_id):
    """Delete or safely archive a course from the platform."""
    course = get_object_or_404(Course, id=course_id)
    title = course.title
    force_delete = request.POST.get("force_delete") in ["true", "1", "yes"]

    has_enrollments = course.enrollments.exists()
    has_orders = course.order_items.exists()

    # If course has active enrollments or financial transactions and force_delete is not set,
    # safely archive it instead of hard-deleting to prevent breaking student learning & order records.
    if (has_enrollments or has_orders) and not force_delete:
        course.status = CourseStatus.ARCHIVED
        course.save(update_fields=["status"])

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.COURSE_UNPUBLISHED,
            object_type="Course",
            object_id=str(course_id),
            object_repr=title,
            changes={
                "status": CourseStatus.ARCHIVED,
                "reason": "Archived instead of hard-deleted due to existing learner enrollments/orders.",
            },
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        enrolled_count = course.enrollments.count()
        messages.warning(
            request,
            f"Course '{title}' has {enrolled_count} enrolled learner(s) or associated purchase history. "
            f"To preserve student learning records, it has been moved to 'Archived' status and unpublished from the marketplace. "
            f"If you intend to completely remove all data, use the Purge action under the Archived tab.",
        )
        return redirect("admin_panel:course_list")

    try:
        with transaction.atomic():
            if force_delete:
                course.enrollments.all().delete()
                course.order_items.all().delete()
            course.delete()

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.COURSE_DELETED,
            object_type="Course",
            object_id=str(course_id),
            object_repr=title,
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        messages.success(request, f"Course '{title}' has been successfully deleted.")
    except ProtectedError:
        course.status = CourseStatus.ARCHIVED
        course.save(update_fields=["status"])
        messages.warning(
            request,
            f"Course '{title}' is referenced by other protected records and cannot be permanently deleted. "
            f"It has been safely moved to 'Archived' status instead.",
        )

    return redirect("admin_panel:course_list")


@admin_required
@require_http_methods(["POST"])
def section_create_view(request, course_id):
    """Create a new curriculum section inside a course."""
    course = get_object_or_404(Course, id=course_id)
    title = request.POST.get("title", "").strip()
    description = request.POST.get("description", "").strip()

    if not title:
        messages.error(request, "Section title is required.")
        return redirect("admin_panel:course_curriculum", course_id=course.id)

    next_order = course.sections.count() + 1
    Section.objects.create(
        course=course,
        title=title,
        description=description,
        order=next_order,
        is_published=True,
    )
    messages.success(request, f"Section '{title}' added.")
    return redirect("admin_panel:course_curriculum", course_id=course.id)


@admin_required
@require_http_methods(["POST"])
def section_delete_view(request, section_id):
    """Delete a curriculum section."""
    section = get_object_or_404(Section, id=section_id)
    course_id = section.course_id
    section.delete()
    messages.success(request, "Section removed.")
    return redirect("admin_panel:course_curriculum", course_id=course_id)


@admin_required
@require_http_methods(["POST"])
def lecture_create_view(request, section_id):
    """Create a lecture inside a section."""
    section = get_object_or_404(Section, id=section_id)
    title = request.POST.get("title", "").strip()
    description = request.POST.get("description", "").strip()
    is_preview = request.POST.get("is_free_preview") == "on"
    duration = int(request.POST.get("estimated_duration", "0") or 0)

    if not title:
        messages.error(request, "Lecture title is required.")
        return redirect("admin_panel:course_curriculum", course_id=section.course_id)

    next_order = section.lectures.count() + 1
    lecture = Lecture.objects.create(
        section=section,
        title=title,
        description=description,
        is_free_preview=is_preview,
        is_published=True,
        estimated_duration=duration * 60,
        order=next_order,
    )

    # Optional video file upload
    if "video_file" in request.FILES:
        video_file = request.FILES["video_file"]
        from apps.storage.service import get_storage_service
        storage = get_storage_service()
        key = f"courses/{section.course_id}/videos/{lecture.id}_{video_file.name}"
        storage.upload_file(key, video_file, content_type=video_file.content_type)
        LectureVideo.objects.create(
            lecture=lecture,
            storage_key=key,
            original_filename=video_file.name,
            file_size_bytes=video_file.size,
            mime_type=video_file.content_type or "video/mp4",
        )

    # Optional PDF note upload
    if "note_file" in request.FILES:
        note_file = request.FILES["note_file"]
        from apps.storage.service import get_storage_service
        storage = get_storage_service()
        key = f"courses/{section.course_id}/notes/{lecture.id}_{note_file.name}"
        storage.upload_file(key, note_file, content_type="application/pdf")
        LectureNote.objects.create(
            lecture=lecture,
            title=f"Notes: {title}",
            note_type=NoteType.PDF,
            storage_key=key,
            original_filename=note_file.name,
            file_size_bytes=note_file.size,
        )

    messages.success(request, f"Lecture '{title}' added.")
    return redirect("admin_panel:course_curriculum", course_id=section.course_id)


@admin_required
@require_http_methods(["POST"])
def lecture_delete_view(request, lecture_id):
    """Delete a lecture."""
    lecture = get_object_or_404(Lecture, id=lecture_id)
    course_id = lecture.section.course_id
    lecture.delete()
    messages.success(request, "Lecture removed.")
    return redirect("admin_panel:course_curriculum", course_id=course_id)


@admin_required
@require_http_methods(["POST"])
def study_material_upload_view(request, lecture_id):
    """Admin upload of lecture study material, document, or attachment."""
    from apps.storage.service import get_storage_service, safe_filename, validate_document_file

    lecture = get_object_or_404(Lecture.objects.select_related("section"), id=lecture_id)
    course_id = lecture.section.course_id

    title = request.POST.get("title", "").strip()
    material_type = request.POST.get("material_type", "note").lower()
    file_obj = request.FILES.get("file") or request.FILES.get("note_file")
    html_content = request.POST.get("html_content", "").strip()

    if file_obj:
        is_valid, error = validate_document_file(file_obj)
        if not is_valid:
            messages.error(request, error)
            return redirect("admin_panel:course_curriculum", course_id=course_id)

        storage = get_storage_service()
        clean_name = safe_filename(file_obj.name)
        storage_key = f"courses/{course_id}/materials/{lecture.id}_{clean_name}"
        storage.upload_file(storage_key, file_obj, content_type=getattr(file_obj, "content_type", "application/octet-stream"))

        if material_type == "attachment" or clean_name.lower().endswith((".zip", ".tar", ".gz")):
            Attachment.objects.create(
                lecture=lecture,
                title=title or file_obj.name,
                storage_key=storage_key,
                original_filename=file_obj.name,
                mime_type=getattr(file_obj, "content_type", "application/octet-stream"),
                file_size_bytes=file_obj.size,
                is_downloadable=True,
            )
            messages.success(request, f"Attachment '{title or file_obj.name}' uploaded successfully.")
        else:
            note_type = NoteType.PDF if clean_name.lower().endswith(".pdf") else NoteType.OTHER
            LectureNote.objects.create(
                lecture=lecture,
                title=title or file_obj.name,
                note_type=note_type,
                storage_key=storage_key,
                original_filename=file_obj.name,
                file_size_bytes=file_obj.size,
                mime_type=getattr(file_obj, "content_type", "application/pdf"),
                is_downloadable=True,
            )
            messages.success(request, f"Study material '{title or file_obj.name}' uploaded successfully.")

    elif html_content:
        LectureNote.objects.create(
            lecture=lecture,
            title=title or "Lecture Note",
            note_type=NoteType.HTML,
            html_content=html_content,
        )
        messages.success(request, "Lecture note created successfully.")
    else:
        messages.error(request, "Please choose a file to upload or enter text content.")

    return redirect("admin_panel:course_curriculum", course_id=course_id)


@admin_required
@require_http_methods(["POST"])
def study_material_delete_view(request, material_type, material_id):
    """Admin deletion of study material or attachment."""
    from apps.storage.service import StorageService

    if material_type == "note":
        item = get_object_or_404(LectureNote.objects.select_related("lecture__section"), id=material_id)
        course_id = item.lecture.section.course_id
    elif material_type == "attachment":
        item = get_object_or_404(Attachment.objects.select_related("lecture__section"), id=material_id)
        course_id = item.lecture.section.course_id
    else:
        messages.error(request, "Invalid material type.")
        return redirect("admin_panel:course_list")

    if item.storage_key:
        try:
            StorageService.delete_file(item.storage_key)
        except Exception as exc:
            logger.warning("Failed to delete storage key %s: %s", item.storage_key, exc)

    title = item.title
    item.delete()
    messages.success(request, f"Study material '{title}' removed.")
    return redirect("admin_panel:course_curriculum", course_id=course_id)


# ─────────────────────────────────────────────────────────────────────────────
# 3. TRANSACTIONS & ORDERS MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

@admin_required
def transaction_list_view(request):
    """List all orders / transactions with search, status filters, and stats."""
    qs = Order.objects.select_related("user", "invoice").prefetch_related("items").order_by("-created_at")

    search = request.GET.get("q", "").strip()
    if search:
        qs = qs.filter(
            Q(order_number__icontains=search)
            | Q(payment_transaction_id__icontains=search)
            | Q(user__email__icontains=search)
            | Q(billing_name__icontains=search)
            | Q(billing_email__icontains=search)
        )

    status = request.GET.get("status", "").strip()
    if status in OrderStatus.values:
        qs = qs.filter(status=status)

    provider = request.GET.get("provider", "").strip()
    if provider:
        qs = qs.filter(payment_provider__iexact=provider)

    # Financial Summary
    total_rev = Order.objects.filter(status=OrderStatus.COMPLETED).aggregate(s=Sum("total"))["s"] or Decimal("0.00")
    completed_count = Order.objects.filter(status=OrderStatus.COMPLETED).count()
    refunded_count = Order.objects.filter(status=OrderStatus.REFUNDED).count()

    context = {
        "active_tab": "transactions",
        "orders": qs,
        "search_query": search,
        "selected_status": status,
        "selected_provider": provider,
        "total_revenue": total_rev,
        "completed_count": completed_count,
        "refunded_count": refunded_count,
    }
    return render(request, "dashboard/admin/transactions/list.html", context)


@admin_required
def transaction_detail_view(request, order_id):
    """Deep-dive transaction details view with full financial breakdown, raw gateway data, and refund controls."""
    order = get_object_or_404(
        Order.objects.select_related("user").prefetch_related(
            "items__course",
            "payments",
            "enrollments",
        ),
        id=order_id,
    )

    invoice = getattr(order, "invoice", None)
    payments = list(order.payments.all())
    active_enrollments = list(order.enrollments.all())

    context = {
        "active_tab": "transactions",
        "order": order,
        "invoice": invoice,
        "payments": payments,
        "enrollments": active_enrollments,
    }
    return render(request, "dashboard/admin/transactions/detail.html", context)


@admin_required
@require_http_methods(["POST"])
def transaction_refund_view(request, order_id):
    """Admin action to refund an order and revoke enrolled access."""
    order = get_object_or_404(Order, id=order_id)
    reason = request.POST.get("refund_reason", "Customer request").strip()

    order.status = OrderStatus.REFUNDED
    order.notes = f"{order.notes}\n[Admin Refund] {timezone.now().strftime('%Y-%m-%d %H:%M')}: {reason}"
    order.save(update_fields=["status", "notes"])

    # Update payment record if exists
    Payment.objects.filter(order=order).update(
        status=PaymentStatus.REFUNDED,
        refund_amount=order.total,
        refunded_at=timezone.now(),
    )

    # Revoke course access
    revoked_count = Enrollment.objects.filter(order=order).update(status=EnrollmentStatus.REVOKED)

    # Audit log
    AuditLog.objects.create(
        actor=request.user,
        action=AuditAction.REFUND_ISSUED,
        object_type="Order",
        object_id=str(order.id),
        object_repr=order.order_number,
        changes={"refund_amount": str(order.total), "reason": reason, "revoked_enrollments": revoked_count},
        ip_address=request.META.get("REMOTE_ADDR"),
    )

    messages.success(request, f"Order #{order.order_number} refunded. {revoked_count} enrollment(s) revoked.")
    return redirect("admin_panel:transaction_detail", order_id=order.id)


# ─────────────────────────────────────────────────────────────────────────────
# 4. COUPONS & PROMOTIONS MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

@admin_required
def coupon_list_view(request):
    """List and manage discount coupons."""
    coupons = Coupon.objects.select_related("created_by").order_by("-created_at")

    context = {
        "active_tab": "coupons",
        "coupons": coupons,
        "total_count": coupons.count(),
        "active_count": coupons.filter(is_active=True).count(),
    }
    return render(request, "dashboard/admin/coupons/list.html", context)


@admin_required
@require_http_methods(["GET", "POST"])
def coupon_create_view(request):
    """Create a new discount coupon."""
    if request.method == "POST":
        code = request.POST.get("code", "").strip().upper()
        discount_type = request.POST.get("discount_type", DiscountType.PERCENTAGE)
        val_raw = request.POST.get("discount_value", "10").strip()
        max_disc_raw = request.POST.get("max_discount_amount", "").strip()
        min_order_raw = request.POST.get("minimum_order_amount", "0").strip()
        max_uses_raw = request.POST.get("max_uses", "").strip()
        valid_days = int(request.POST.get("valid_days", "30") or 30)

        errors = []
        if not code:
            errors.append("Coupon code is required.")
        elif Coupon.objects.filter(code=code).exists():
            errors.append(f"Coupon with code '{code}' already exists.")

        try:
            discount_value = Decimal(val_raw)
            if discount_value <= 0:
                errors.append("Discount value must be greater than zero.")
        except Exception:
            errors.append("Invalid discount value.")
            discount_value = Decimal("10.00")

        max_disc = Decimal(max_disc_raw) if max_disc_raw else None
        min_order = Decimal(min_order_raw) if min_order_raw else Decimal("0.00")
        max_uses = int(max_uses_raw) if max_uses_raw else None

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(request, "dashboard/admin/coupons/form.html", {
                "active_tab": "coupons",
                "form_data": request.POST,
            })

        now = timezone.now()
        coupon = Coupon.objects.create(
            code=code,
            discount_type=discount_type,
            discount_value=discount_value,
            max_discount_amount=max_disc,
            minimum_order_amount=min_order,
            max_uses=max_uses,
            valid_from=now,
            valid_until=now + timedelta(days=valid_days),
            is_active=True,
            created_by=request.user,
        )

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.COUPON_CREATED,
            object_type="Coupon",
            object_id=str(coupon.id),
            object_repr=coupon.code,
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        messages.success(request, f"Coupon '{coupon.code}' created successfully!")
        return redirect("admin_panel:coupon_list")

    return render(request, "dashboard/admin/coupons/form.html", {"active_tab": "coupons", "form_data": {}})


@admin_required
@require_http_methods(["POST"])
def coupon_toggle_view(request, coupon_id):
    """Toggle coupon active/inactive status."""
    coupon = get_object_or_404(Coupon, id=coupon_id)
    coupon.is_active = not coupon.is_active
    coupon.save(update_fields=["is_active"])
    status_label = "activated" if coupon.is_active else "deactivated"
    messages.info(request, f"Coupon '{coupon.code}' {status_label}.")
    return redirect("admin_panel:coupon_list")


@admin_required
@require_http_methods(["POST"])
def coupon_delete_view(request, coupon_id):
    """Delete a coupon."""
    coupon = get_object_or_404(Coupon, id=coupon_id)
    code = coupon.code
    coupon.delete()
    messages.success(request, f"Coupon '{code}' removed.")
    return redirect("admin_panel:coupon_list")


# ─────────────────────────────────────────────────────────────────────────────
# 5. ENROLLMENTS MANAGEMENT (MANUAL ENROLLMENT, REVOCATION)
# ─────────────────────────────────────────────────────────────────────────────

@admin_required
def enrollment_list_view(request):
    """List all student enrollments across all courses."""
    qs = Enrollment.objects.select_related("user", "course", "order").order_by("-created_at")

    search = request.GET.get("q", "").strip()
    if search:
        qs = qs.filter(
            Q(user__email__icontains=search)
            | Q(course__title__icontains=search)
            | Q(order__order_number__icontains=search)
        )

    status = request.GET.get("status", "").strip()
    if status in EnrollmentStatus.values:
        qs = qs.filter(status=status)

    context = {
        "active_tab": "enrollments",
        "enrollments": qs,
        "search_query": search,
        "selected_status": status,
        "total_count": Enrollment.objects.count(),
        "active_count": Enrollment.objects.filter(status=EnrollmentStatus.ACTIVE).count(),
    }
    return render(request, "dashboard/admin/enrollments/list.html", context)


@admin_required
@require_http_methods(["GET", "POST"])
def enrollment_create_view(request):
    """Manually enroll a student into a course."""
    students = User.objects.filter(is_active=True).order_by("email")
    courses = Course.objects.all().order_by("title")

    if request.method == "POST":
        user_id = request.POST.get("user_id")
        course_id = request.POST.get("course_id")

        if not user_id or not course_id:
            messages.error(request, "Please select both a student and a course.")
            return redirect("admin_panel:enrollment_create")

        user = get_object_or_404(User, id=user_id)
        course = get_object_or_404(Course, id=course_id)

        enrollment, created = Enrollment.objects.get_or_create(
            user=user,
            course=course,
            defaults={
                "status": EnrollmentStatus.ACTIVE,
                "access_type": AccessType.LIFETIME,
            },
        )
        if not created:
            enrollment.status = EnrollmentStatus.ACTIVE
            enrollment.save(update_fields=["status"])

        # Initialize progress
        from apps.progress.models import CourseProgress
        CourseProgress.objects.get_or_create(enrollment=enrollment)

        # Update course count
        course.enrollment_count = course.enrollments.filter(status=EnrollmentStatus.ACTIVE).count()
        course.save(update_fields=["enrollment_count"])

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.ENROLLMENT_CREATED,
            object_type="Enrollment",
            object_id=str(enrollment.id),
            object_repr=f"{user.email} -> {course.title}",
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        messages.success(request, f"Successfully enrolled {user.email} in '{course.title}'!")
        return redirect("admin_panel:enrollment_list")

    return render(request, "dashboard/admin/enrollments/form.html", {
        "active_tab": "enrollments",
        "students": students,
        "courses": courses,
    })


@admin_required
@require_http_methods(["POST"])
def enrollment_toggle_view(request, enrollment_id):
    """Toggle an enrollment between ACTIVE and REVOKED."""
    enrollment = get_object_or_404(Enrollment, id=enrollment_id)
    if enrollment.status == EnrollmentStatus.ACTIVE:
        enrollment.status = EnrollmentStatus.REVOKED
        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.ENROLLMENT_REVOKED,
            object_type="Enrollment",
            object_id=str(enrollment.id),
            object_repr=str(enrollment),
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        messages.info(request, f"Course access revoked for {enrollment.user.email}.")
    else:
        enrollment.status = EnrollmentStatus.ACTIVE
        messages.success(request, f"Course access restored for {enrollment.user.email}.")

    enrollment.save(update_fields=["status"])
    return redirect(request.META.get("HTTP_REFERER") or "admin_panel:enrollment_list")


# ─────────────────────────────────────────────────────────────────────────────
# 6. USERS MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

@admin_required
def user_list_view(request):
    """List all platform users with role filters and search."""
    qs = User.objects.select_related("profile").annotate(
        enrollment_count=Count("enrollments"),
        order_count=Count("orders"),
    ).order_by("-date_joined")

    role = request.GET.get("role")
    if role:
        qs = qs.filter(role=role)

    search = request.GET.get("q")
    if search:
        qs = qs.filter(
            Q(email__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
        )

    status = request.GET.get("status")
    if status == "active":
        qs = qs.filter(is_active=True, is_suspended=False)
    elif status == "suspended":
        qs = qs.filter(is_suspended=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)

    context = {
        "active_tab": "users",
        "users": qs,
        "roles": ["admin", "teacher", "student"],
        "total_users": User.objects.count(),
        "total_students": User.objects.filter(role="student").count(),
        "total_teachers": User.objects.filter(role="teacher").count(),
    }
    return render(request, "dashboard/admin/users.html", context)


@admin_required
@require_http_methods(["GET", "POST"])
def user_create_view(request):
    """Create a new user account directly from admin console."""
    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        password = request.POST.get("password", "")
        role = request.POST.get("role", "student")
        verified = request.POST.get("email_verified") == "on"

        errors = []
        if not email:
            errors.append("Email address is required.")
        elif User.objects.filter(email=email).exists():
            errors.append(f"A user with email '{email}' already exists.")
        if not password or len(password) < 8:
            errors.append("Password must be at least 8 characters long.")

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(request, "dashboard/admin/users/form.html", {
                "active_tab": "users",
                "form_data": request.POST,
            })

        user = User.objects.create_user(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role=role,
            email_verified=verified,
        )

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.USER_CREATED,
            object_type="User",
            object_id=str(user.id),
            object_repr=user.email,
            changes={"role": role, "email_verified": verified},
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        messages.success(request, f"User account '{user.email}' created with role '{role}'.")
        return redirect("admin_panel:user_list")

    return render(request, "dashboard/admin/users/form.html", {"active_tab": "users", "form_data": {}})


@admin_required
def user_detail_view(request, user_id):
    """View complete user profile, orders, and enrollments."""
    user = get_object_or_404(User, id=user_id)
    enrollments = Enrollment.objects.filter(user=user).select_related("course")
    orders = Order.objects.filter(user=user).order_by("-created_at")
    context = {
        "active_tab": "users",
        "profile_user": user,
        "enrollments": enrollments,
        "orders": orders,
    }
    return render(request, "dashboard/admin/user_detail.html", context)


@admin_required
@require_http_methods(["POST"])
def change_user_role_view(request, user_id):
    """Change a user's role and verification status."""
    user = get_object_or_404(User, id=user_id)
    new_role = request.POST.get("role")
    if new_role in ["student", "teacher", "admin"]:
        old_role = user.role
        user.role = new_role
        user.is_staff = (new_role == "admin")
        user.save(update_fields=["role", "is_staff"])

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.ROLE_CHANGED,
            object_type="User",
            object_id=str(user.id),
            object_repr=user.email,
            changes={"from": old_role, "to": new_role},
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        messages.success(request, f"User role updated to '{new_role}'.")

    return redirect("admin_panel:user_detail", user_id=user.id)


@admin_required
def suspend_user_view(request, user_id):
    if request.method == "POST":
        user = get_object_or_404(User, id=user_id)
        reason = request.POST.get("reason", "")
        AccountService.suspend_user(user, reason=reason, actor=request.user)
        messages.success(request, f"User {user.email} has been suspended.")
    return redirect("admin_panel:user_detail", user_id=user_id)


@admin_required
def activate_user_view(request, user_id):
    if request.method == "POST":
        user = get_object_or_404(User, id=user_id)
        AccountService.activate_user(user, actor=request.user)
        messages.success(request, f"User {user.email} has been activated.")
    return redirect("admin_panel:user_detail", user_id=user_id)


# ─────────────────────────────────────────────────────────────────────────────
# 7. AUDIT LOGS & REPORTS
# ─────────────────────────────────────────────────────────────────────────────

@admin_required
def audit_log_view(request):
    """View tamper-evident security and activity audit trail."""
    action_filter = request.GET.get("action", "").strip()
    logs = AuditLog.objects.select_related("actor").order_by("-created_at")
    if action_filter:
        logs = logs.filter(action=action_filter)

    context = {
        "active_tab": "audit_logs",
        "logs": logs[:150],
        "action_filter": action_filter,
        "actions": AuditAction.choices,
    }
    return render(request, "dashboard/admin/audit_logs.html", context)


@admin_required
def analytics_view(request):
    return render(request, "dashboard/admin/analytics.html", {"active_tab": "analytics"})


@admin_required
def reports_view(request):
    return render(request, "dashboard/admin/reports.html", {"active_tab": "reports"})


@admin_required
def revenue_report_view(request):
    orders = Order.objects.filter(status=OrderStatus.COMPLETED).select_related("user").order_by("-created_at")
    total_revenue = orders.aggregate(total=Sum("total"))["total"] or Decimal("0.00")
    context = {
        "active_tab": "transactions",
        "orders": orders,
        "total_revenue": total_revenue,
    }
    return render(request, "dashboard/admin/revenue_report.html", context)


@admin_required
def student_report_view(request):
    students = User.objects.filter(role="student").annotate(
        enrollment_count=Count("enrollments")
    ).order_by("-date_joined")
    return render(request, "dashboard/admin/student_report.html", {
        "active_tab": "users",
        "students": students,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 8. CATEGORY MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

@admin_required
def category_list_view(request):
    """Admin interface to list, search, and manage course categories."""
    q = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "")

    categories = Category.objects.select_related("parent").annotate(
        course_count=Count("courses")
    ).order_by("order", "name")

    if q:
        categories = categories.filter(
            Q(name__icontains=q) | Q(slug__icontains=q) | Q(description__icontains=q)
        )

    if status_filter == "active":
        categories = categories.filter(is_active=True)
    elif status_filter == "inactive":
        categories = categories.filter(is_active=False)

    total_categories = Category.objects.count()
    active_categories = Category.objects.filter(is_active=True).count()
    root_categories = Category.objects.filter(parent__isnull=True).count()
    total_courses_categorized = Course.objects.filter(category__isnull=False).count()

    context = {
        "active_tab": "categories",
        "categories": categories,
        "q": q,
        "status_filter": status_filter,
        "total_categories": total_categories,
        "active_categories": active_categories,
        "root_categories": root_categories,
        "total_courses_categorized": total_courses_categorized,
    }
    return render(request, "dashboard/admin/categories/list.html", context)


@admin_required
@require_http_methods(["GET", "POST"])
def category_create_view(request):
    """Admin interface to create a new category."""
    parent_categories = Category.objects.order_by("name")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        slug = request.POST.get("slug", "").strip()
        icon = request.POST.get("icon", "").strip()
        description = request.POST.get("description", "").strip()
        parent_id = request.POST.get("parent_id")
        order_raw = request.POST.get("order", "0").strip()
        is_active = request.POST.get("is_active") == "on"

        errors = []
        if not name:
            errors.append("Category name is required.")
        elif Category.objects.filter(name__iexact=name).exists():
            errors.append(f"Category with name '{name}' already exists.")

        if not slug:
            slug = slugify(name)
        else:
            slug = slugify(slug)

        if Category.objects.filter(slug=slug).exists():
            errors.append(f"Category with slug '{slug}' already exists.")

        try:
            order = int(order_raw) if order_raw else 0
            if order < 0:
                order = 0
        except ValueError:
            order = 0

        parent = None
        if parent_id:
            parent = Category.objects.filter(id=parent_id).first()

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(request, "dashboard/admin/categories/form.html", {
                "active_tab": "categories",
                "parent_categories": parent_categories,
                "form_data": request.POST,
                "is_create": True,
            })

        category = Category.objects.create(
            name=name,
            slug=slug,
            icon=icon or "📚",
            description=description,
            parent=parent,
            order=order,
            is_active=is_active,
        )

        if "image" in request.FILES:
            category.image = request.FILES["image"]
            category.save(update_fields=["image"])

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.SETTINGS_CHANGED,
            object_type="Category",
            object_id=str(category.id),
            object_repr=category.name,
            changes={"action": "created", "name": category.name, "slug": category.slug},
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        messages.success(request, f"Category '{category.name}' created successfully.")
        return redirect("admin_panel:category_list")

    return render(request, "dashboard/admin/categories/form.html", {
        "active_tab": "categories",
        "parent_categories": parent_categories,
        "is_create": True,
    })


@admin_required
@require_http_methods(["GET", "POST"])
def category_edit_view(request, category_id):
    """Admin interface to edit an existing category."""
    category = get_object_or_404(Category, id=category_id)
    parent_categories = Category.objects.exclude(id=category.id).order_by("name")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        slug = request.POST.get("slug", "").strip()
        icon = request.POST.get("icon", "").strip()
        description = request.POST.get("description", "").strip()
        parent_id = request.POST.get("parent_id")
        order_raw = request.POST.get("order", "0").strip()
        is_active = request.POST.get("is_active") == "on"

        errors = []
        if not name:
            errors.append("Category name is required.")
        elif Category.objects.filter(name__iexact=name).exclude(id=category.id).exists():
            errors.append(f"Another category with name '{name}' already exists.")

        if not slug:
            slug = slugify(name)
        else:
            slug = slugify(slug)

        if Category.objects.filter(slug=slug).exclude(id=category.id).exists():
            errors.append(f"Another category with slug '{slug}' already exists.")

        try:
            order = int(order_raw) if order_raw else 0
            if order < 0:
                order = 0
        except ValueError:
            order = 0

        parent = None
        if parent_id and parent_id != str(category.id):
            parent = Category.objects.filter(id=parent_id).first()

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(request, "dashboard/admin/categories/form.html", {
                "active_tab": "categories",
                "category": category,
                "parent_categories": parent_categories,
                "is_create": False,
            })

        category.name = name
        category.slug = slug
        category.icon = icon or "📚"
        category.description = description
        category.parent = parent
        category.order = order
        category.is_active = is_active

        if "image" in request.FILES:
            category.image = request.FILES["image"]

        category.save()

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.SETTINGS_CHANGED,
            object_type="Category",
            object_id=str(category.id),
            object_repr=category.name,
            changes={"action": "updated", "name": category.name, "slug": category.slug},
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        messages.success(request, f"Category '{category.name}' updated successfully.")
        return redirect("admin_panel:category_list")

    return render(request, "dashboard/admin/categories/form.html", {
        "active_tab": "categories",
        "category": category,
        "parent_categories": parent_categories,
        "is_create": False,
    })


@admin_required
@require_http_methods(["POST"])
def category_toggle_view(request, category_id):
    """Toggle a category's active state."""
    category = get_object_or_404(Category, id=category_id)
    category.is_active = not category.is_active
    category.save(update_fields=["is_active", "updated_at"])

    AuditLog.objects.create(
        actor=request.user,
        action=AuditAction.SETTINGS_CHANGED,
        object_type="Category",
        object_id=str(category.id),
        object_repr=category.name,
        changes={"is_active": category.is_active},
        ip_address=request.META.get("REMOTE_ADDR"),
    )

    state = "active" if category.is_active else "inactive"
    messages.success(request, f"Category '{category.name}' is now {state}.")
    return redirect("admin_panel:category_list")


@admin_required
@require_http_methods(["POST"])
def category_delete_view(request, category_id):
    """Safely delete a category."""
    category = get_object_or_404(Category, id=category_id)
    cat_name = category.name
    courses_count = category.courses.count()

    # Detach subcategories
    category.subcategories.update(parent=None)

    # Delete category (courses.category becomes NULL due to SET_NULL)
    category.delete()

    AuditLog.objects.create(
        actor=request.user,
        action=AuditAction.SETTINGS_CHANGED,
        object_type="Category",
        object_id=str(category_id),
        object_repr=cat_name,
        changes={"action": "deleted", "unlinked_courses": courses_count},
        ip_address=request.META.get("REMOTE_ADDR"),
    )

    messages.success(
        request,
        f"Category '{cat_name}' has been deleted." + (f" ({courses_count} course(s) unlinked)" if courses_count else "")
    )
    return redirect("admin_panel:category_list")
