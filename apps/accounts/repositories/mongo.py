"""MongoDB account repository; all Mongo-specific mapping stays in this adapter."""
from datetime import datetime, timezone
from uuid import UUID, uuid4

from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from infrastructure.database.exceptions import (
    DatabaseConnectionError,
    EntityConflictError,
    EntityNotFoundError,
    RepositoryError,
)
from infrastructure.database.mongodb import get_mongo_database

from .base import (
    AccountRecord,
    GroupGrant,
    PasswordResetRecord,
    PermissionGrant,
    ProfileRecord,
    VerificationTokenRecord,
)


class MongoAccountRepository:
    """Implements account CRUD with ObjectId storage and UUID public identifiers."""
    collection_name = "accounts"

    @staticmethod
    def _as_utc(value):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @staticmethod
    def _permission_grant(document):
        return PermissionGrant(
            id=str(document["id"]), codename=document["codename"], name=document["name"],
            app_label=document["app_label"], model=document["model"],
        )

    @classmethod
    def _profile_record(cls, document):
        if document is None:
            return None
        return ProfileRecord(
            avatar_path=document.get("avatar_path"), bio=document.get("bio", ""),
            phone=document.get("phone", ""), website=document.get("website", ""),
            linkedin=document.get("linkedin", ""), twitter=document.get("twitter", ""),
            github=document.get("github", ""), country=document.get("country", ""),
            city=document.get("city", ""), timezone=document.get("timezone", "Asia/Kolkata"),
            notification_email=document.get("notification_email", True),
            notification_new_lecture=document.get("notification_new_lecture", True),
            notification_course_updates=document.get("notification_course_updates", True),
            created_at=cls._as_utc(document["created_at"]),
            updated_at=cls._as_utc(document["updated_at"]),
        )

    def __init__(self, database=None):
        self.collection = (database if database is not None else get_mongo_database())[self.collection_name]
        try:
            self.collection.create_index([("public_id", ASCENDING)], unique=True)
            self.collection.create_index([("email", ASCENDING)], unique=True)
            self.collection.create_index([("username", ASCENDING)], unique=True, sparse=True)
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not initialize account indexes.") from exc

    @staticmethod
    def _record(document):
        if not document:
            raise EntityNotFoundError("Account was not found.")
        return AccountRecord(
            id=str(document["public_id"]), email=document["email"], password_hash=document["password_hash"],
            username=document.get("username", ""), first_name=document.get("first_name", ""),
            last_name=document.get("last_name", ""), role=document.get("role", "student"),
            is_active=document.get("is_active", True), email_verified=document.get("email_verified", False),
            date_joined=MongoAccountRepository._as_utc(document["date_joined"]),
            is_staff=document.get("is_staff", False),
            is_superuser=document.get("is_superuser", False),
            last_login=MongoAccountRepository._as_utc(document.get("last_login")),
            is_suspended=document.get("is_suspended", False),
            suspended_reason=document.get("suspended_reason", ""),
            suspended_at=MongoAccountRepository._as_utc(document.get("suspended_at")),
            two_factor_enabled=document.get("two_factor_enabled", False),
            two_factor_secret=document.get("two_factor_secret", ""),
            two_factor_backup_codes=tuple(document.get("two_factor_backup_codes", ())),
            group_ids=tuple(document.get("group_ids", ())),
            permission_ids=tuple(document.get("permission_ids", ())),
            groups=tuple(
                GroupGrant(
                    id=str(group["id"]), name=group["name"],
                    permissions=tuple(MongoAccountRepository._permission_grant(permission)
                                      for permission in group.get("permissions", ())),
                )
                for group in document.get("groups", ())
            ),
            direct_permissions=tuple(
                MongoAccountRepository._permission_grant(permission)
                for permission in document.get("direct_permissions", ())
            ),
            profile=MongoAccountRepository._profile_record(document.get("profile")),
            verification_tokens=tuple(
                VerificationTokenRecord(
                    id=str(item["id"]), token=str(item["token"]),
                    created_at=MongoAccountRepository._as_utc(item["created_at"]),
                    expires_at=MongoAccountRepository._as_utc(item["expires_at"]),
                    used_at=MongoAccountRepository._as_utc(item.get("used_at")),
                )
                for item in document.get("verification_tokens", ())
            ),
            password_reset_tokens=tuple(
                PasswordResetRecord(
                    id=str(item["id"]), token=str(item["token"]),
                    created_at=MongoAccountRepository._as_utc(item["created_at"]),
                    expires_at=MongoAccountRepository._as_utc(item["expires_at"]),
                    used_at=MongoAccountRepository._as_utc(item.get("used_at")),
                    ip_address=item.get("ip_address"),
                )
                for item in document.get("password_reset_tokens", ())
            ),
        )

    def create(self, *, email, password_hash, username="", first_name="", last_name="", role="student"):
        document = {
            "public_id": str(uuid4()), "email": email, "password_hash": password_hash, "username": username,
            "first_name": first_name, "last_name": last_name, "role": role, "is_active": True,
            "email_verified": False, "date_joined": datetime.now(timezone.utc),
            "is_staff": False, "is_superuser": False, "last_login": None,
            "is_suspended": False, "suspended_reason": "", "suspended_at": None,
            "two_factor_enabled": False, "two_factor_secret": "", "two_factor_backup_codes": [],
            "group_ids": [], "permission_ids": [], "groups": [], "direct_permissions": [],
            "profile": {
                "avatar_path": None, "bio": "", "phone": "", "website": "", "linkedin": "",
                "twitter": "", "github": "", "country": "", "city": "", "timezone": "Asia/Kolkata",
                "notification_email": True, "notification_new_lecture": True,
                "notification_course_updates": True, "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            },
            "verification_tokens": [], "password_reset_tokens": [],
        }
        try:
            self.collection.insert_one(document)
            return self._record(document)
        except DuplicateKeyError as exc:
            raise EntityConflictError("An account with that email or username already exists.") from exc
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not save the account.") from exc

    def import_sql_record(self, user, *, source_revision=None):
        """Copy an SQL identity; revisions enable ordered live projection from the outbox."""
        def permission_data(permission):
            return {
                "id": str(permission.pk), "codename": permission.codename, "name": permission.name,
                "app_label": permission.content_type.app_label, "model": permission.content_type.model,
            }

        groups = []
        for group in user.groups.prefetch_related("permissions__content_type").all():
            permissions = [permission_data(permission) for permission in group.permissions.all()]
            permissions.sort(key=lambda item: (item["app_label"], item["model"], item["codename"]))
            groups.append({
                "id": str(group.pk), "name": group.name,
                "permissions": permissions,
            })
        groups.sort(key=lambda item: (item["name"], item["id"]))
        direct_permissions = [
            permission_data(permission)
            for permission in user.user_permissions.select_related("content_type").all()
        ]
        direct_permissions.sort(key=lambda item: (item["app_label"], item["model"], item["codename"]))
        verification_tokens = [{
            "id": str(item.pk), "token": str(item.token), "created_at": item.created_at,
            "expires_at": item.expires_at, "used_at": item.used_at,
        } for item in user.email_verifications.all()]
        verification_tokens.sort(key=lambda item: (item["created_at"], item["id"]))
        password_reset_tokens = [{
            "id": str(item.pk), "token": str(item.token), "created_at": item.created_at,
            "expires_at": item.expires_at, "used_at": item.used_at, "ip_address": item.ip_address,
        } for item in user.password_resets.all()]
        password_reset_tokens.sort(key=lambda item: (item["created_at"], item["id"]))

        profile = getattr(user, "profile", None)
        try:
            avatar_path = profile.avatar.name if profile and profile.avatar else None
        except (ValueError, OSError):
            avatar_path = None

        document = {
            "public_id": str(user.pk), "email": user.email, "password_hash": user.password,
            "username": user.username, "first_name": user.first_name, "last_name": user.last_name,
            "role": user.role, "is_active": user.is_active, "email_verified": user.email_verified,
            "date_joined": user.date_joined, "is_staff": user.is_staff,
            "is_superuser": user.is_superuser, "last_login": user.last_login,
            "is_suspended": user.is_suspended, "suspended_reason": user.suspended_reason,
            "suspended_at": user.suspended_at, "two_factor_enabled": user.two_factor_enabled,
            "two_factor_secret": user.two_factor_secret,
            "two_factor_backup_codes": list(user.two_factor_backup_codes or ()),
            "group_ids": [str(pk) for pk in user.groups.values_list("pk", flat=True)],
            "permission_ids": [str(pk) for pk in user.user_permissions.values_list("pk", flat=True)],
            "groups": groups, "direct_permissions": direct_permissions,
            "profile": ({
                "avatar_path": avatar_path, "bio": profile.bio, "phone": profile.phone,
                "website": profile.website, "linkedin": profile.linkedin, "twitter": profile.twitter,
                "github": profile.github, "country": profile.country, "city": profile.city,
                "timezone": profile.timezone, "notification_email": profile.notification_email,
                "notification_new_lecture": profile.notification_new_lecture,
                "notification_course_updates": profile.notification_course_updates,
                "created_at": profile.created_at, "updated_at": profile.updated_at,
            } if profile else None),
            "verification_tokens": verification_tokens,
            "password_reset_tokens": password_reset_tokens,
            "deleted": False,
        }
        try:
            if source_revision is None:
                result = self.collection.update_one(
                    {"public_id": document["public_id"]}, {"$setOnInsert": document}, upsert=True
                )
                return result.upserted_id is not None
            self.collection.update_one(
                {"public_id": document["public_id"]},
                [{"$replaceWith": {"$cond": [
                    {"$gt": [source_revision, {"$ifNull": ["$source_revision", -1]}]},
                    {"$mergeObjects": ["$$ROOT", {**document, "source_revision": source_revision}]},
                    "$$ROOT",
                ]}}],
                upsert=True,
            )
            return True
        except DuplicateKeyError as exc:
            raise EntityConflictError("An imported account conflicts with an existing email or username.") from exc
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not import the SQL account.") from exc

    def delete_by_id(self, account_id, *, source_revision):
        """Tombstone a deleted account so an older retry cannot recreate it."""
        identifier = str(account_id)
        try:
            self.collection.update_one(
                {"public_id": identifier},
                [{"$replaceWith": {"$cond": [
                    {"$gt": [source_revision, {"$ifNull": ["$source_revision", -1]}]},
                    {"$mergeObjects": ["$$ROOT", {
                        "public_id": identifier, "deleted": True, "source_revision": source_revision,
                    }]},
                    "$$ROOT",
                ]}}],
                upsert=True,
            )
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not tombstone the SQL account.") from exc

    def get_by_id(self, account_id):
        try:
            identifier = str(UUID(str(account_id)))
            document = self.collection.find_one({"public_id": identifier, "deleted": {"$ne": True}})
            return self._record(document)
        except (ValueError, TypeError) as exc:
            raise EntityNotFoundError("Account was not found.") from exc
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not retrieve the account.") from exc

    def update(self, account_id, changes):
        allowed = {"username", "first_name", "last_name", "role", "is_active", "email_verified", "password_hash"}
        if changes.keys() - allowed:
            raise RepositoryError("Unsupported account update field.")
        try:
            identifier = str(UUID(str(account_id)))
            document = self.collection.find_one_and_update(
                {"public_id": identifier}, {"$set": changes}, return_document=ReturnDocument.AFTER
            )
            return self._record(document)
        except (ValueError, TypeError) as exc:
            raise EntityNotFoundError("Account was not found.") from exc
        except DuplicateKeyError as exc:
            raise EntityConflictError("The update conflicts with an existing account.") from exc
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not update the account.") from exc

    def delete(self, account_id):
        try:
            identifier = str(UUID(str(account_id)))
            result = self.collection.delete_one({"public_id": identifier})
            if result.deleted_count != 1:
                raise EntityNotFoundError("Account was not found.")
        except (ValueError, TypeError) as exc:
            raise EntityNotFoundError("Account was not found.") from exc
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not delete the account.") from exc

    def list(self, *, limit=100, offset=0):
        if not 1 <= limit <= 500 or offset < 0:
            raise RepositoryError("Account list pagination is outside the allowed range.")
        try:
            cursor = self.collection.find({"deleted": {"$ne": True}}).sort("email", ASCENDING).skip(offset).limit(limit)
            return [self._record(document) for document in cursor]
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not list accounts.") from exc
