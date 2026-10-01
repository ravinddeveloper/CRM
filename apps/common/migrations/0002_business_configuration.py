from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("common", "0001_platformsettings")]
    operations = [
        migrations.AddField(
            model_name="platformsettings", name="business_type",
            field=models.CharField(choices=[("learning", "Learning and courses"), ("dance", "Dance studio"), ("fitness", "Fitness classes"), ("gym", "Gym and membership"), ("studio", "Studio and workshops"), ("coaching", "Coaching"), ("other", "Other service business")], default="learning", max_length=24),
        ),
        migrations.AddField(model_name="platformsettings", name="member_label", field=models.CharField(default="Student", max_length=48)),
        migrations.AddField(model_name="platformsettings", name="staff_label", field=models.CharField(default="Teacher", max_length=48)),
        migrations.AddField(model_name="platformsettings", name="class_label", field=models.CharField(default="Class", max_length=48)),
        migrations.AddField(model_name="platformsettings", name="schedule_label", field=models.CharField(default="Schedule", max_length=48)),
        migrations.AddField(model_name="platformsettings", name="allow_staff_check_in", field=models.BooleanField(default=True)),
        migrations.AddField(model_name="platformsettings", name="require_staff_location", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="platformsettings", name="require_member_location", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="platformsettings", name="attendance_radius_meters", field=models.PositiveIntegerField(default=150)),
        migrations.AddField(model_name="platformsettings", name="max_location_accuracy_meters", field=models.PositiveIntegerField(default=150)),
        migrations.AddField(model_name="platformsettings", name="attendance_latitude", field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
        migrations.AddField(model_name="platformsettings", name="attendance_longitude", field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
        migrations.AddField(model_name="platformsettings", name="check_in_early_minutes", field=models.PositiveSmallIntegerField(default=30)),
        migrations.AddField(model_name="platformsettings", name="check_in_late_minutes", field=models.PositiveSmallIntegerField(default=20)),
    ]
