from django.contrib import admin

from .models import MemberMembership, MembershipPlan, Session, SessionBooking, StaffShift


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("title", "session_type", "starts_at", "ends_at", "instructor", "status", "capacity")
    list_filter = ("status", "session_type", "starts_at", "membership_required")
    search_fields = ("title", "location_name", "instructor__email")
    autocomplete_fields = ("instructor",)
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "starts_at"


@admin.register(SessionBooking)
class SessionBookingAdmin(admin.ModelAdmin):
    list_display = ("session", "member", "status", "booked_at", "checked_in_at", "check_in_distance_meters")
    list_filter = ("status", "booked_at", "checked_in_at")
    search_fields = ("session__title", "member__email", "member__first_name", "member__last_name")
    autocomplete_fields = ("session", "member")
    readonly_fields = ("booked_at", "created_at", "updated_at", "check_in_distance_meters", "location_accuracy_meters")


@admin.register(StaffShift)
class StaffShiftAdmin(admin.ModelAdmin):
    list_display = ("employee", "checked_in_at", "checked_out_at", "check_in_distance_meters", "check_out_distance_meters")
    list_filter = ("checked_in_at", "checked_out_at")
    search_fields = ("employee__email", "employee__first_name", "employee__last_name")
    autocomplete_fields = ("employee",)
    readonly_fields = tuple(field.name for field in StaffShift._meta.fields if field.name != "employee")


@admin.register(MembershipPlan)
class MembershipPlanAdmin(admin.ModelAdmin):
    list_display = ("name", "duration_days", "price", "currency", "is_active")
    list_filter = ("is_active", "currency")
    search_fields = ("name",)


@admin.register(MemberMembership)
class MemberMembershipAdmin(admin.ModelAdmin):
    list_display = ("member", "plan", "status", "starts_at", "ends_at")
    list_filter = ("status", "plan")
    search_fields = ("member__email", "plan__name")
    autocomplete_fields = ("member", "plan")
