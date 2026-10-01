"""Account service - business logic for auth and user management."""
import logging
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from infrastructure.database.config import DatabaseEngine, get_database_engine
from infrastructure.database.exceptions import ApplicationValidationError, EntityConflictError

from .models import EmailVerificationToken, PasswordResetToken, Profile

User = get_user_model()
logger = logging.getLogger("apps.accounts")


class AccountService:
    """Service for account-related business logic."""

    @staticmethod
    @transaction.atomic
    def register_user(email: str, password: str, first_name: str, last_name: str, username: str = "") -> User:
        """Register a new student user."""
        email = email.lower().strip()

        if User.objects.filter(email=email).exists():
            raise ValidationError("An account with this email already exists.")

        # Auto-generate username if not provided
        if not username:
            base = email.split("@")[0]
            username = base
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base}{counter}"
                counter += 1

        if get_database_engine() is DatabaseEngine.SQL:
            from .repository_service import AccountRepositoryService

            try:
                account = AccountRepositoryService().create_user(
                    email=email, password=password, first_name=first_name,
                    last_name=last_name, username=username, role="student",
                )
                user = User.objects.get(pk=account.id)
            except (ApplicationValidationError, EntityConflictError) as exc:
                raise ValidationError(str(exc)) from exc
        else:
            # Django authentication, sessions, and the account's dependent SQL
            # records are not Mongo-backed yet. Preserve the working auth path
            # until that whole aggregate can be cut over together.
            user = User.objects.create_user(
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                username=username,
                role="student",
            )

        # Ensure profile exists (handled safely alongside post_save signal)
        Profile.objects.get_or_create(user=user)

        # Create email verification token
        AccountService._create_verification_token(user)

        logger.info("New user registered: %s", email)
        return user

    @staticmethod
    def _create_verification_token(user: User) -> EmailVerificationToken:
        """Create a new email verification token."""
        # Invalidate old tokens
        EmailVerificationToken.objects.filter(user=user, used_at__isnull=True).update(
            used_at=timezone.now()
        )
        token = EmailVerificationToken.objects.create(user=user)
        return token

    @staticmethod
    def verify_email(token_str: str) -> User:
        """Verify a user's email address using a token."""
        try:
            token_uuid = uuid.UUID(str(token_str))
            token = EmailVerificationToken.objects.select_related("user").get(token=token_uuid)
        except (ValueError, EmailVerificationToken.DoesNotExist):
            raise ValidationError("Invalid verification token.")

        if not token.is_valid:
            raise ValidationError("Verification token has expired or already been used.")

        user = token.user
        user.email_verified = True
        user.save(update_fields=["email_verified"])
        token.mark_used()

        logger.info("Email verified for user: %s", user.email)
        return user

    @staticmethod
    def resend_verification_email(email: str) -> EmailVerificationToken:
        """Resend email verification token."""
        try:
            user = User.objects.get(email=email.lower())
        except User.DoesNotExist:
            # Don't reveal whether the email exists
            return None

        if user.email_verified:
            raise ValidationError("Email is already verified.")

        return AccountService._create_verification_token(user)

    @staticmethod
    def create_password_reset_token(email: str, ip_address: str = None) -> PasswordResetToken | None:
        """Initiate password reset for an email."""
        try:
            user = User.objects.get(email=email.lower(), is_active=True)
        except User.DoesNotExist:
            # Silently ignore to prevent email enumeration
            logger.info("Password reset requested for non-existent email: %s", email)
            return None

        # Invalidate old tokens
        PasswordResetToken.objects.filter(user=user, used_at__isnull=True).update(
            used_at=timezone.now()
        )

        token = PasswordResetToken.objects.create(user=user, ip_address=ip_address)
        logger.info("Password reset token created for: %s", email)
        return token

    @staticmethod
    def reset_password(token_str: str, new_password: str) -> User:
        """Reset a user's password using a token."""
        try:
            token_uuid = uuid.UUID(str(token_str))
            token = PasswordResetToken.objects.select_related("user").get(token=token_uuid)
        except (ValueError, PasswordResetToken.DoesNotExist):
            raise ValidationError("Invalid or expired password reset token.")

        if not token.is_valid:
            raise ValidationError("Password reset token has expired or already been used.")

        user = token.user
        user.set_password(new_password)
        user.save(update_fields=["password"])
        token.mark_used()

        logger.info("Password reset successful for: %s", user.email)
        return user

    @staticmethod
    def change_password(user: User, old_password: str, new_password: str) -> None:
        """Change user password, verifying the old password."""
        if not user.check_password(old_password):
            raise ValidationError("Current password is incorrect.")
        user.set_password(new_password)
        user.save(update_fields=["password"])
        logger.info("Password changed for user: %s", user.email)

    @staticmethod
    def update_profile(user: User, **kwargs) -> Profile:
        """Update user profile fields."""
        profile = user.profile
        allowed_fields = [
            "bio", "phone", "website", "linkedin", "twitter",
            "github", "country", "city", "timezone",
            "notification_email", "notification_new_lecture", "notification_course_updates",
        ]
        for field in allowed_fields:
            if field in kwargs:
                setattr(profile, field, kwargs[field])
        profile.save()

        # Update User model fields
        user_fields = ["first_name", "last_name", "username"]
        changed = []
        for field in user_fields:
            if field in kwargs:
                setattr(user, field, kwargs[field])
                changed.append(field)
        if changed:
            user.save(update_fields=changed)

        return profile

    @staticmethod
    def suspend_user(user: User, reason: str = "", actor: User = None) -> None:
        """Suspend a user account."""
        user.suspend(reason=reason)
        logger.warning("User suspended: %s by %s — reason: %s", user.email, actor, reason)

    @staticmethod
    def activate_user(user: User, actor: User = None) -> None:
        """Reactivate a suspended user account."""
        user.activate()
        logger.info("User activated: %s by %s", user.email, actor)
