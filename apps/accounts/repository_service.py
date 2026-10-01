"""Backend-neutral account CRUD service for the repository migration slice."""
import re
from uuid import uuid4

from django.contrib.auth.hashers import make_password

from infrastructure.database.exceptions import ApplicationValidationError
from infrastructure.database.factory import get_account_repository


class AccountRepositoryService:
    """Account CRUD rules shared by SQL and Mongo repository implementations."""

    def __init__(self, repository=None):
        self.repository = repository or get_account_repository()

    def create_user(self, *, email, password, first_name="", last_name="", username="", role="student"):
        normalized_email = str(email).strip().lower()
        if len(normalized_email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized_email):
            raise ApplicationValidationError("Enter a valid email address.")
        if not isinstance(password, str) or len(password) < 8:
            raise ApplicationValidationError("Password must contain at least 8 characters.")
        clean_username = str(username).strip() or f"account_{uuid4().hex[:16]}"
        if len(clean_username) > 150:
            raise ApplicationValidationError("Username cannot exceed 150 characters.")
        if len(str(first_name)) > 150 or len(str(last_name)) > 150:
            raise ApplicationValidationError("First and last names cannot exceed 150 characters.")
        if role not in {"admin", "teacher", "employee", "student"}:
            raise ApplicationValidationError("Choose a supported account role.")
        return self.repository.create(
            email=normalized_email,
            password_hash=make_password(password),
            username=clean_username,
            first_name=str(first_name).strip(),
            last_name=str(last_name).strip(),
            role=role,
        )

    def get_user(self, user_id):
        return self.repository.get_by_id(str(user_id))

    def update_user(self, user_id, changes):
        allowed = {"username", "first_name", "last_name", "role", "is_active", "email_verified"}
        if changes.keys() - allowed:
            raise ApplicationValidationError("One or more account fields cannot be changed.")
        if "role" in changes and changes["role"] not in {"admin", "teacher", "employee", "student"}:
            raise ApplicationValidationError("Choose a supported account role.")
        for field in ("username", "first_name", "last_name"):
            if field in changes and len(str(changes[field])) > 150:
                raise ApplicationValidationError(f"{field.replace('_', ' ').capitalize()} cannot exceed 150 characters.")
        for field in ("is_active", "email_verified"):
            if field in changes and not isinstance(changes[field], bool):
                raise ApplicationValidationError(f"{field.replace('_', ' ').capitalize()} must be true or false.")
        if not changes:
            return self.repository.get_by_id(str(user_id))
        return self.repository.update(str(user_id), changes)

    def delete_user(self, user_id):
        self.repository.delete(str(user_id))

    def list_users(self, *, limit=100, offset=0):
        if not 1 <= limit <= 500 or offset < 0:
            raise ApplicationValidationError("Use a limit from 1 to 500 and a non-negative offset.")
        return self.repository.list(limit=limit, offset=offset)
