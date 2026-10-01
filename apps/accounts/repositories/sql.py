"""SQL account repository backed by the existing Django user model."""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, DatabaseError

from infrastructure.database.exceptions import (
    DatabaseConnectionError,
    EntityConflictError,
    EntityNotFoundError,
    RepositoryError,
)

from .base import (
    AccountRecord,
    GroupGrant,
    PasswordResetRecord,
    PermissionGrant,
    ProfileRecord,
    VerificationTokenRecord,
)


class SQLAccountRepository:
    """Implements the portable account contract using Django ORM."""

    @staticmethod
    def _related_ids(user, relation_name):
        prefetched = getattr(user, "_prefetched_objects_cache", {})
        related = prefetched.get(relation_name)
        if related is None:
            related = getattr(user, relation_name).all()
        return tuple(str(item.pk) for item in related)

    @staticmethod
    def _permission_grant(permission):
        content_type = permission.content_type
        return PermissionGrant(
            id=str(permission.pk), codename=permission.codename, name=permission.name,
            app_label=content_type.app_label, model=content_type.model,
        )

    @staticmethod
    def _related(user, relation_name):
        prefetched = getattr(user, "_prefetched_objects_cache", {})
        related = prefetched.get(relation_name)
        if related is None:
            related = getattr(user, relation_name).all()
        return related

    @classmethod
    def _groups(cls, user):
        groups = []
        for group in cls._related(user, "groups"):
            permissions = sorted(
                (cls._permission_grant(permission) for permission in cls._related(group, "permissions")),
                key=lambda item: (item.app_label, item.model, item.codename),
            )
            groups.append(GroupGrant(id=str(group.pk), name=group.name, permissions=tuple(permissions)))
        return tuple(sorted(groups, key=lambda item: (item.name, item.id)))

    @staticmethod
    def _profile(user):
        profile = getattr(user, "profile", None)
        if profile is None:
            return None
        try:
            avatar_path = profile.avatar.name if profile.avatar else None
        except (ValueError, OSError):
            avatar_path = None
        return ProfileRecord(
            avatar_path=avatar_path, bio=profile.bio, phone=profile.phone, website=profile.website,
            linkedin=profile.linkedin, twitter=profile.twitter, github=profile.github,
            country=profile.country, city=profile.city, timezone=profile.timezone,
            notification_email=profile.notification_email,
            notification_new_lecture=profile.notification_new_lecture,
            notification_course_updates=profile.notification_course_updates,
            created_at=profile.created_at, updated_at=profile.updated_at,
        )

    @classmethod
    def _verification_tokens(cls, user):
        tokens = [
            VerificationTokenRecord(
                id=str(item.pk), token=str(item.token), created_at=item.created_at,
                expires_at=item.expires_at, used_at=item.used_at,
            )
            for item in cls._related(user, "email_verifications")
        ]
        return tuple(sorted(tokens, key=lambda item: (item.created_at, item.id)))

    @classmethod
    def _password_reset_tokens(cls, user):
        tokens = [
            PasswordResetRecord(
                id=str(item.pk), token=str(item.token), created_at=item.created_at,
                expires_at=item.expires_at, used_at=item.used_at, ip_address=item.ip_address,
            )
            for item in cls._related(user, "password_resets")
        ]
        return tuple(sorted(tokens, key=lambda item: (item.created_at, item.id)))

    @staticmethod
    def _record(user) -> AccountRecord:
        return AccountRecord(
            id=str(user.id), email=user.email, password_hash=user.password, username=user.username,
            first_name=user.first_name, last_name=user.last_name, role=user.role,
            is_active=user.is_active, email_verified=user.email_verified, date_joined=user.date_joined,
            is_staff=user.is_staff, is_superuser=user.is_superuser, last_login=user.last_login,
            is_suspended=user.is_suspended, suspended_reason=user.suspended_reason,
            suspended_at=user.suspended_at, two_factor_enabled=user.two_factor_enabled,
            two_factor_secret=user.two_factor_secret,
            two_factor_backup_codes=tuple(user.two_factor_backup_codes or ()),
            group_ids=SQLAccountRepository._related_ids(user, "groups"),
            permission_ids=SQLAccountRepository._related_ids(user, "user_permissions"),
            groups=SQLAccountRepository._groups(user),
            direct_permissions=tuple(sorted(
                (SQLAccountRepository._permission_grant(permission)
                 for permission in SQLAccountRepository._related(user, "user_permissions")),
                key=lambda item: (item.app_label, item.model, item.codename),
            )),
            profile=SQLAccountRepository._profile(user),
            verification_tokens=SQLAccountRepository._verification_tokens(user),
            password_reset_tokens=SQLAccountRepository._password_reset_tokens(user),
        )

    def create(self, *, email, password_hash, username="", first_name="", last_name="", role="student"):
        User = get_user_model()
        try:
            user = User(email=email, username=username, first_name=first_name, last_name=last_name, role=role)
            user.password = password_hash
            user.save(force_insert=True)
            return self._record(user)
        except IntegrityError as exc:
            raise EntityConflictError("An account with that email or username already exists.") from exc
        except DatabaseError as exc:
            raise DatabaseConnectionError("The SQL database could not save the account.") from exc
        except DjangoValidationError as exc:
            raise RepositoryError("The account data was rejected by the SQL repository.") from exc

    def get_by_id(self, account_id):
        User = get_user_model()
        try:
            user = User.objects.prefetch_related(
                "groups__permissions__content_type", "user_permissions__content_type", "profile",
                "email_verifications", "password_resets",
            ).get(pk=account_id)
            return self._record(user)
        except (User.DoesNotExist, ValueError, DjangoValidationError) as exc:
            raise EntityNotFoundError("Account was not found.") from exc
        except DatabaseError as exc:
            raise DatabaseConnectionError("The SQL database could not retrieve the account.") from exc

    def update(self, account_id, changes):
        User = get_user_model()
        allowed = {"username", "first_name", "last_name", "role", "is_active", "email_verified", "password_hash"}
        if changes.keys() - allowed:
            raise RepositoryError("Unsupported account update field.")
        try:
            user = User.objects.get(pk=account_id)
            for field, value in changes.items():
                setattr(user, "password" if field == "password_hash" else field, value)
            user.save(update_fields=["password" if field == "password_hash" else field for field in changes])
            return self._record(user)
        except (User.DoesNotExist, ValueError, DjangoValidationError) as exc:
            raise EntityNotFoundError("Account was not found.") from exc
        except IntegrityError as exc:
            raise EntityConflictError("The update conflicts with an existing account.") from exc
        except DatabaseError as exc:
            raise DatabaseConnectionError("The SQL database could not update the account.") from exc

    def delete(self, account_id):
        User = get_user_model()
        try:
            deleted, _ = User.objects.filter(pk=account_id).delete()
            if not deleted:
                raise EntityNotFoundError("Account was not found.")
        except (ValueError, DjangoValidationError) as exc:
            raise EntityNotFoundError("Account was not found.") from exc
        except DatabaseError as exc:
            raise DatabaseConnectionError("The SQL database could not delete the account.") from exc

    def list(self, *, limit=100, offset=0):
        if not 1 <= limit <= 500 or offset < 0:
            raise RepositoryError("Account list pagination is outside the allowed range.")
        User = get_user_model()
        try:
            users = User.objects.prefetch_related(
                "groups__permissions__content_type", "user_permissions__content_type", "profile",
                "email_verifications", "password_resets",
            ).order_by("email")[offset:offset + limit]
            return [self._record(user) for user in users]
        except DatabaseError as exc:
            raise DatabaseConnectionError("The SQL database could not list accounts.") from exc
