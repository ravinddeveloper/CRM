"""Backend-neutral account repository contract and result type."""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PermissionGrant:
    id: str
    codename: str
    name: str
    app_label: str
    model: str


@dataclass(frozen=True, slots=True)
class GroupGrant:
    id: str
    name: str
    permissions: tuple[PermissionGrant, ...] = ()


@dataclass(frozen=True, slots=True)
class ProfileRecord:
    avatar_path: str | None
    bio: str
    phone: str
    website: str
    linkedin: str
    twitter: str
    github: str
    country: str
    city: str
    timezone: str
    notification_email: bool
    notification_new_lecture: bool
    notification_course_updates: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class VerificationTokenRecord:
    id: str
    token: str
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None


@dataclass(frozen=True, slots=True)
class PasswordResetRecord:
    id: str
    token: str
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None
    ip_address: str | None


@dataclass(frozen=True, slots=True)
class AccountRecord:
    id: str
    email: str
    password_hash: str
    username: str
    first_name: str
    last_name: str
    role: str
    is_active: bool
    email_verified: bool
    date_joined: datetime
    is_staff: bool = False
    is_superuser: bool = False
    last_login: datetime | None = None
    is_suspended: bool = False
    suspended_reason: str = ""
    suspended_at: datetime | None = None
    two_factor_enabled: bool = False
    two_factor_secret: str = ""
    two_factor_backup_codes: tuple[str, ...] = ()
    group_ids: tuple[str, ...] = ()
    permission_ids: tuple[str, ...] = ()
    groups: tuple[GroupGrant, ...] = ()
    direct_permissions: tuple[PermissionGrant, ...] = ()
    profile: ProfileRecord | None = None
    verification_tokens: tuple[VerificationTokenRecord, ...] = ()
    password_reset_tokens: tuple[PasswordResetRecord, ...] = ()


class AccountRepository(Protocol):
    def create(
        self,
        *,
        email: str,
        password_hash: str,
        username: str = "",
        first_name: str = "",
        last_name: str = "",
        role: str = "student",
    ) -> AccountRecord: ...

    def get_by_id(self, account_id: str) -> AccountRecord: ...
    def update(self, account_id: str, changes: dict) -> AccountRecord: ...
    def delete(self, account_id: str) -> None: ...
    def list(self, *, limit: int = 100, offset: int = 0) -> list[AccountRecord]: ...
