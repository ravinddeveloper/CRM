import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.contrib.auth.models import Group, Permission
from django.utils import timezone

from apps.accounts.repositories.sql import SQLAccountRepository
from apps.accounts.models import EmailVerificationToken, PasswordResetToken
from apps.accounts.services import AccountService

pytestmark = pytest.mark.django_db


def test_sql_registration_uses_account_repository_and_keeps_auth_side_effects():
    from unittest.mock import patch

    repository = SQLAccountRepository()
    with patch(
        "apps.accounts.repository_service.get_account_repository", return_value=repository
    ) as get_repository:
        user = AccountService.register_user(
            email="Repository.User@example.com", password="SecurePass123!",
            first_name="Repository", last_name="User", username="repository-user",
        )

    get_repository.assert_called_once_with()
    assert user.email == "repository.user@example.com"
    assert check_password("SecurePass123!", user.password)
    assert user.profile is not None
    assert EmailVerificationToken.objects.filter(user=user, used_at__isnull=True).exists()


def test_sql_account_record_preserves_auth_security_state_and_relations():
    User = get_user_model()
    user = User.objects.create_superuser(
        email="privileged@example.com", password="strong-test-password", username="privileged",
    )
    group = Group.objects.create(name="course managers")
    permission = Permission.objects.order_by("pk").first()
    user.groups.add(group)
    if permission:
        group.permissions.add(permission)
        user.user_permissions.add(permission)
    user.last_login = timezone.now()
    user.is_suspended = True
    user.suspended_reason = "security review"
    user.suspended_at = timezone.now()
    user.two_factor_enabled = True
    user.two_factor_secret = "JBSWY3DPEHPK3PXP"
    user.two_factor_backup_codes = ["A1B2C3D4"]
    user.save()
    user.profile.bio = "Profile content"
    user.profile.phone = "+1-555-0100"
    user.profile.notification_new_lecture = False
    user.profile.save()
    verification = EmailVerificationToken.objects.create(user=user)
    reset = PasswordResetToken.objects.create(user=user, ip_address="192.0.2.30")

    repository = SQLAccountRepository()
    record = repository.get_by_id(str(user.pk))
    listed = next(item for item in repository.list(limit=100) if item.id == str(user.pk))

    assert record.is_staff is True
    assert record.is_superuser is True
    assert record.last_login == user.last_login
    assert record.is_suspended is True
    assert record.suspended_reason == "security review"
    assert record.suspended_at == user.suspended_at
    assert record.two_factor_enabled is True
    assert record.two_factor_secret == "JBSWY3DPEHPK3PXP"
    assert record.two_factor_backup_codes == ("A1B2C3D4",)
    assert record.group_ids == (str(group.pk),)
    assert record.groups[0].name == group.name
    assert record.profile.bio == "Profile content"
    assert record.profile.phone == "+1-555-0100"
    assert record.profile.notification_new_lecture is False
    assert record.verification_tokens[0].id == str(verification.pk)
    assert record.verification_tokens[0].token == str(verification.token)
    assert record.password_reset_tokens[0].id == str(reset.pk)
    assert record.password_reset_tokens[0].ip_address == "192.0.2.30"
    if permission:
        assert record.permission_ids == (str(permission.pk),)
        assert listed.permission_ids == (str(permission.pk),)
        assert record.groups[0].permissions[0].codename == permission.codename
        assert record.direct_permissions[0].app_label == permission.content_type.app_label
    assert listed.group_ids == (str(group.pk),)
