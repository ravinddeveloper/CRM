from django.contrib import admin
from django.core.cache import cache
from django import forms
from django.conf import settings

from .models import PlatformSettings
from .theme import FIELD_NAMES, PALETTE_DEFAULTS, get_portal_colors


class PlatformSettingsForm(forms.ModelForm):
    class Meta:
        model = PlatformSettings
        fields = "__all__"
        widgets = {
            field: forms.TextInput(attrs={"type": "color", "style": "width:4rem;height:2.5rem;padding:.2rem"})
            for field in (
                "primary_color", "accent_color", "background_color", "surface_color", "raised_surface_color",
                "text_color", "muted_text_color", "border_color", "inverse_text_color", "success_color",
                "warning_color", "error_color", "info_color",
                "invoice_background_color", "invoice_surface_color", "invoice_text_color",
                "invoice_muted_text_color", "invoice_border_color",
            )
        }


@admin.register(PlatformSettings)
class PlatformSettingsAdmin(admin.ModelAdmin):
    form = PlatformSettingsForm
    fieldsets = (
        ("Website identity", {"fields": ("name", "tagline", "logo", "favicon", "website_url")}),
        ("Portal color palette", {"description": "These colors theme the portal, dashboard, forms, status badges, buttons, emails, and generated invoices. Environment variables provide defaults for a new settings record; saved admin values are used afterward.", "fields": (
            "primary_color", "accent_color", "background_color", "surface_color", "raised_surface_color",
            "text_color", "muted_text_color", "border_color", "inverse_text_color",
            "success_color", "warning_color", "error_color", "info_color",
        )}),
        ("Invoice colors", {"fields": (
            "invoice_background_color", "invoice_surface_color", "invoice_text_color",
            "invoice_muted_text_color", "invoice_border_color",
        )}),
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

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        env_palette = get_portal_colors({
            field: getattr(settings, f"PORTAL_{token.upper()}_COLOR", PALETTE_DEFAULTS[token])
            for token, field in FIELD_NAMES.items()
        })
        initial.update({FIELD_NAMES[token]: color for token, color in env_palette.items()})
        return initial

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        cache.delete("common.platform_settings")
