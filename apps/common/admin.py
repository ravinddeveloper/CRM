from django.contrib import admin
from django.core.cache import cache

from .models import PlatformSettings


@admin.register(PlatformSettings)
class PlatformSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Website identity", {"fields": ("name", "tagline", "logo", "favicon", "primary_color", "website_url")}),
        ("Contact", {"fields": ("support_email",)}),
        ("Invoices and billing", {"fields": ("legal_name", "billing_address", "tax_registration_number", "invoice_footer")}),
        ("Business setup", {"fields": (
            "business_type", "member_label", "staff_label", "class_label", "schedule_label",
        )}),
        ("Attendance rules", {"fields": (
            "allow_staff_check_in", "require_staff_location", "require_member_location",
            "attendance_latitude", "attendance_longitude", "attendance_radius_meters",
            "max_location_accuracy_meters", "check_in_early_minutes", "check_in_late_minutes",
        )}),
    )

    def has_add_permission(self, request):
        try:
            return not PlatformSettings.objects.exists()
        except Exception:
            return True

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        cache.delete("common.platform_settings")
