import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("common", "0002_business_configuration"),
        ("courses", "0001_initial"),
        ("accounts", "0003_employee_role"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="MembershipPlan",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True)),
                ("duration_days", models.PositiveIntegerField(blank=True, help_text="Leave blank for no expiry.", null=True)),
                ("price", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("currency", models.CharField(default="INR", max_length=3)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Session",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                ("session_type", models.CharField(choices=[("in_person", "In person"), ("live_online", "Live online"), ("hybrid", "Hybrid"), ("appointment", "Appointment")], default="in_person", max_length=20)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("scheduled", "Scheduled"), ("cancelled", "Cancelled"), ("completed", "Completed")], default="scheduled", max_length=20)),
                ("starts_at", models.DateTimeField(db_index=True)),
                ("ends_at", models.DateTimeField()),
                ("location_name", models.CharField(blank=True, max_length=160)),
                ("address", models.TextField(blank=True)),
                ("meeting_url", models.URLField(blank=True, help_text="Private meeting link shown only to booked members.")),
                ("latitude", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ("longitude", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ("geofence_radius_meters", models.PositiveIntegerField(blank=True, null=True)),
                ("capacity", models.PositiveIntegerField(default=0, help_text="0 means unlimited.")),
                ("booking_required", models.BooleanField(default=True)),
                ("attendance_required", models.BooleanField(default=True)),
                ("membership_required", models.BooleanField(default=False)),
                ("allow_waitlist", models.BooleanField(default=True)),
                ("course", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="scheduled_sessions", to="courses.course")),
                ("instructor", models.ForeignKey(blank=True, limit_choices_to=models.Q(("role__in", ["teacher", "employee", "admin"])), null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="scheduled_sessions", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["starts_at"],
                "indexes": [
                    models.Index(fields=["status", "starts_at"], name="session_status_start_idx"),
                    models.Index(fields=["instructor", "starts_at"], name="session_instructor_start_idx"),
                ],
                "constraints": [models.CheckConstraint(condition=models.Q(("ends_at__gt", models.F("starts_at"))), name="session_end_after_start")],
            },
        ),
        migrations.CreateModel(
            name="MemberMembership",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(choices=[("active", "Active"), ("paused", "Paused"), ("expired", "Expired"), ("cancelled", "Cancelled")], default="active", max_length=20)),
                ("starts_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("ends_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.CharField(blank=True, max_length=240)),
                ("member", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to=settings.AUTH_USER_MODEL)),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="memberships", to="scheduling.membershipplan")),
            ],
            options={
                "ordering": ["-starts_at"],
                "indexes": [models.Index(fields=["member", "status", "ends_at"], name="membership_member_status_idx")],
            },
        ),
        migrations.CreateModel(
            name="SessionBooking",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(choices=[("booked", "Booked"), ("waitlisted", "Waitlisted"), ("cancelled", "Cancelled")], default="booked", max_length=20)),
                ("booked_at", models.DateTimeField(auto_now_add=True)),
                ("checked_in_at", models.DateTimeField(blank=True, null=True)),
                ("check_in_distance_meters", models.PositiveIntegerField(blank=True, null=True)),
                ("location_accuracy_meters", models.PositiveIntegerField(blank=True, null=True)),
                ("member", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="session_bookings", to=settings.AUTH_USER_MODEL)),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bookings", to="scheduling.session")),
            ],
            options={
                "ordering": ["booked_at"],
                "indexes": [
                    models.Index(fields=["member", "status"], name="booking_member_status_idx"),
                    models.Index(fields=["session", "status"], name="booking_session_status_idx"),
                ],
                "constraints": [models.UniqueConstraint(fields=("session", "member"), name="unique_session_booking")],
            },
        ),
        migrations.CreateModel(
            name="StaffShift",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("checked_in_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("checked_out_at", models.DateTimeField(blank=True, null=True)),
                ("check_in_distance_meters", models.PositiveIntegerField(blank=True, null=True)),
                ("check_out_distance_meters", models.PositiveIntegerField(blank=True, null=True)),
                ("check_in_accuracy_meters", models.PositiveIntegerField(blank=True, null=True)),
                ("check_out_accuracy_meters", models.PositiveIntegerField(blank=True, null=True)),
                ("check_in_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("check_out_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("employee", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="staff_shifts", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-checked_in_at"],
                "indexes": [models.Index(fields=["employee", "checked_in_at"], name="shift_employee_time_idx")],
                "constraints": [
                    models.CheckConstraint(condition=models.Q(("checked_out_at__isnull", True), ("checked_out_at__gte", models.F("checked_in_at")), _connector="OR"), name="staff_shift_checkout_after_checkin"),
                    models.UniqueConstraint(condition=models.Q(("checked_out_at__isnull", True)), fields=("employee",), name="one_open_shift_per_employee"),
                ],
            },
        ),
    ]
