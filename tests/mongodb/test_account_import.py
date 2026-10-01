import os
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    pytest.skip("Set MONGO_URI to run MongoDB integration tests.", allow_module_level=True)

pytest.importorskip("pymongo")
from pymongo import MongoClient

from apps.accounts.models import EmailVerificationToken, PasswordResetToken
from apps.accounts.repositories.mongo import MongoAccountRepository

pytestmark = pytest.mark.django_db


@pytest.fixture
def repository():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1500)
    database = client[f"test_account_import_{uuid4().hex}"]
    try:
        yield MongoAccountRepository(database=database)
    finally:
        client.drop_database(database.name)
        client.close()


def test_import_preserves_identity_password_security_and_permission_references(repository):
    User = get_user_model()
    user = User.objects.create_superuser(
        email="migrate-admin@example.com", password="password-for-migration-test", username="migrate-admin",
    )
    group = Group.objects.create(name="migration-check")
    from django.contrib.auth.models import Permission
    permission = Permission.objects.order_by("pk").first()
    user.groups.add(group)
    if permission:
        group.permissions.add(permission)
        user.user_permissions.add(permission)
    user.profile.bio = "Migrated bio"
    user.profile.notification_course_updates = False
    user.profile.save()
    user.is_suspended = True
    user.suspended_reason = "retained state"
    user.two_factor_enabled = True
    user.two_factor_secret = "JBSWY3DPEHPK3PXP"
    user.two_factor_backup_codes = ["RECOVERY1"]
    user.save()
    verification = EmailVerificationToken.objects.create(user=user)
    reset = PasswordResetToken.objects.create(user=user, ip_address="198.51.100.16")

    assert repository.import_sql_record(user) is True
    assert repository.import_sql_record(user) is False
    imported = repository.get_by_id(str(user.pk))

    assert imported.id == str(user.pk)
    assert imported.password_hash == user.password
    assert imported.is_staff and imported.is_superuser
    assert imported.is_suspended is True
    assert imported.suspended_reason == "retained state"
    assert imported.two_factor_enabled is True
    assert imported.two_factor_secret == user.two_factor_secret
    assert imported.two_factor_backup_codes == ("RECOVERY1",)
    assert imported.group_ids == (str(group.pk),)
    assert imported.groups[0].name == group.name
    assert imported.profile.bio == "Migrated bio"
    assert imported.profile.notification_course_updates is False
    assert imported.verification_tokens[0].token == str(verification.token)
    assert imported.password_reset_tokens[0].token == str(reset.token)
    assert imported.password_reset_tokens[0].ip_address == "198.51.100.16"
    if permission:
        assert imported.groups[0].permissions[0].codename == permission.codename
        assert imported.direct_permissions[0].app_label == permission.content_type.app_label
