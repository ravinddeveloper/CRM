import django.core.validators
from django.db import migrations, models


color_validator = django.core.validators.RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Enter a six-digit hex color such as #4f46e5.")


class Migration(migrations.Migration):
    dependencies = [("common", "0002_business_configuration")]
    operations = [
        migrations.AddField(model_name="platformsettings", name="accent_color", field=models.CharField(default="#7c3aed", max_length=7, validators=[color_validator])),
        migrations.AddField(model_name="platformsettings", name="background_color", field=models.CharField(default="#030712", max_length=7, validators=[color_validator])),
        migrations.AddField(model_name="platformsettings", name="surface_color", field=models.CharField(default="#111827", max_length=7, validators=[color_validator])),
        migrations.AddField(model_name="platformsettings", name="raised_surface_color", field=models.CharField(default="#1f2937", max_length=7, validators=[color_validator])),
        migrations.AddField(model_name="platformsettings", name="text_color", field=models.CharField(default="#f9fafb", max_length=7, validators=[color_validator])),
        migrations.AddField(model_name="platformsettings", name="muted_text_color", field=models.CharField(default="#9ca3af", max_length=7, validators=[color_validator])),
        migrations.AddField(model_name="platformsettings", name="border_color", field=models.CharField(default="#374151", max_length=7, validators=[color_validator])),
        migrations.AddField(model_name="platformsettings", name="inverse_text_color", field=models.CharField(default="#ffffff", max_length=7, validators=[color_validator])),
        migrations.AddField(model_name="platformsettings", name="success_color", field=models.CharField(default="#10b981", max_length=7, validators=[color_validator])),
        migrations.AddField(model_name="platformsettings", name="warning_color", field=models.CharField(default="#f59e0b", max_length=7, validators=[color_validator])),
        migrations.AddField(model_name="platformsettings", name="error_color", field=models.CharField(default="#ef4444", max_length=7, validators=[color_validator])),
        migrations.AddField(model_name="platformsettings", name="info_color", field=models.CharField(default="#3b82f6", max_length=7, validators=[color_validator])),
        migrations.AddField(model_name="platformsettings", name="invoice_background_color", field=models.CharField(default="#ffffff", max_length=7, validators=[color_validator])),
        migrations.AddField(model_name="platformsettings", name="invoice_surface_color", field=models.CharField(default="#f8fafc", max_length=7, validators=[color_validator])),
        migrations.AddField(model_name="platformsettings", name="invoice_text_color", field=models.CharField(default="#1e293b", max_length=7, validators=[color_validator])),
        migrations.AddField(model_name="platformsettings", name="invoice_muted_text_color", field=models.CharField(default="#64748b", max_length=7, validators=[color_validator])),
        migrations.AddField(model_name="platformsettings", name="invoice_border_color", field=models.CharField(default="#e2e8f0", max_length=7, validators=[color_validator])),
    ]
