from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_user_two_factor_backup_codes_user_two_factor_enabled_and_more")]
    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[("admin", "Admin"), ("teacher", "Teacher"), ("employee", "Employee / Staff"), ("student", "Student")],
                db_index=True,
                default="student",
                max_length=20,
            ),
        ),
    ]
