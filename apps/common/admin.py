from django.contrib import admin
from django.core.cache import cache

from .models import PlatformSettings


@admin.register(PlatformSettings)
class PlatformSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Website identity", {"fields": ("name", "tagline", "logo", "favicon", "primary_color", "website_url")}),
        ("Contact", {"fields": ("support_email",)}),
        ("Invoices and billing", {"fields": ("legal_name", "billing_address", "tax_registration_number", "invoice_footer")}),
    )

    def has_add_permission(self, request):
        return not PlatformSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        cache.delete("common.platform_settings")
