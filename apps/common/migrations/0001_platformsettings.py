import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="PlatformSettings",
            fields=[
                ("id", models.PositiveSmallIntegerField(primary_key=True, serialize=False, default=1, editable=False)),
                ("name", models.CharField(max_length=120, default="LearnPro")),
                ("tagline", models.CharField(max_length=200, blank=True, default="")),
                ("logo", models.ImageField(upload_to="branding/", blank=True)),
                ("favicon", models.ImageField(upload_to="branding/", blank=True)),
                ("support_email", models.EmailField(blank=True, max_length=254)),
                ("website_url", models.URLField(blank=True)),
                ("legal_name", models.CharField(max_length=180, blank=True)),
                ("billing_address", models.TextField(blank=True)),
                ("tax_registration_number", models.CharField(max_length=80, blank=True)),
                ("invoice_footer", models.CharField(max_length=240, blank=True)),
                ("primary_color", models.CharField(max_length=7, default="#4f46e5", validators=[django.core.validators.RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Enter a six-digit hex color such as #4f46e5.")])),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "platform settings", "verbose_name_plural": "platform settings"},
        ),
    ]
