"""MongoDB adapter for user notifications."""
from datetime import datetime, timezone
from uuid import UUID, uuid4

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import PyMongoError

from apps.notifications.repositories.base import NotificationRecord
from infrastructure.database.exceptions import DatabaseConnectionError, EntityNotFoundError
from infrastructure.database.mongodb import get_mongo_database


class MongoNotificationRepository:
    """Stores notifications with scalar user IDs and indexed inbox ordering."""
    collection_name = "notifications"

    def __init__(self, database=None):
        self.collection = (database if database is not None else get_mongo_database())[self.collection_name]
        try:
            self.collection.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
            self.collection.create_index([("public_id", ASCENDING)], unique=True)
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not initialize notification indexes.") from exc

    @staticmethod
    def _record(document):
        if not document:
            raise EntityNotFoundError("Notification was not found.")
        return NotificationRecord(
            id=str(document["public_id"]), user_id=str(document["user_id"]),
            notification_type=document["notification_type"], title=document["title"],
            message=document["message"], action_url=document.get("action_url", ""),
            is_read=document.get("is_read", False), read_at=document.get("read_at"),
            created_at=document["created_at"],
        )

    def create(self, *, user_id, notification_type, title, message, action_url):
        document = {
            "public_id": str(uuid4()), "user_id": str(user_id), "notification_type": notification_type,
            "title": title, "message": message, "action_url": action_url, "is_read": False,
            "read_at": None, "created_at": datetime.now(timezone.utc), "deleted": False,
            "source_revision": 0,
        }
        try:
            self.collection.insert_one(document)
            return self._record(document)
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not create the notification.") from exc

    def import_sql_record(self, notification):
        """Idempotently copy a legacy SQL row, retaining public ID and timestamps."""
        document = {
            "public_id": str(notification.pk),
            "user_id": str(notification.user_id),
            "notification_type": notification.notification_type,
            "title": notification.title,
            "message": notification.message,
            "action_url": notification.action_url,
            "is_read": notification.is_read,
            "read_at": notification.read_at,
            "created_at": notification.created_at,
            "deleted": False,
            "source_revision": 0,
        }
        try:
            result = self.collection.update_one(
                {"public_id": document["public_id"]}, {"$setOnInsert": document}, upsert=True
            )
            return result.upserted_id is not None
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not import the SQL notification record.") from exc

    def sync_sql_record(self, notification, *, source_revision):
        """Upsert the current committed SQL state into the Mongo notification inbox."""
        document = {
            "public_id": str(notification.pk), "user_id": str(notification.user_id),
            "notification_type": notification.notification_type, "title": notification.title,
            "message": notification.message, "action_url": notification.action_url,
            "is_read": notification.is_read, "read_at": notification.read_at,
            "created_at": notification.created_at, "deleted": False,
        }
        try:
            self.collection.update_one(
                {"public_id": document["public_id"]},
                [{"$replaceWith": {"$cond": [
                    {"$gt": [source_revision, {"$ifNull": ["$source_revision", -1]}]},
                    {"$mergeObjects": ["$$ROOT", {**document, "source_revision": source_revision}]},
                    "$$ROOT",
                ]}}],
                upsert=True,
            )
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not synchronize the SQL notification.") from exc

    def delete_by_id(self, notification_id, *, source_revision):
        try:
            identifier = str(notification_id)
            self.collection.update_one(
                {"public_id": identifier},
                [{"$replaceWith": {"$cond": [
                    {"$gt": [source_revision, {"$ifNull": ["$source_revision", -1]}]},
                    {"$mergeObjects": ["$$ROOT", {
                        "public_id": identifier, "deleted": True,
                        "deleted_at": datetime.now(timezone.utc), "source_revision": source_revision,
                    }]},
                    "$$ROOT",
                ]}}],
                upsert=True,
            )
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not remove the SQL notification.") from exc

    def list_for_user(self, *, user_id, limit, offset):
        if limit < 1 or offset < 0:
            return 0, []
        try:
            query = {"user_id": str(user_id), "deleted": {"$ne": True}}
            count = self.collection.count_documents(query)
            docs = self.collection.find(query).sort([("created_at", DESCENDING), ("public_id", DESCENDING)]).skip(offset).limit(limit)
            return count, [self._record(item) for item in docs]
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not list notifications.") from exc

    def mark_read(self, *, notification_id, user_id):
        try:
            identifier = str(UUID(str(notification_id)))
            document = self.collection.find_one_and_update(
                {"public_id": identifier, "user_id": str(user_id), "is_read": False, "deleted": {"$ne": True}},
                {"$set": {"is_read": True, "read_at": datetime.now(timezone.utc)}},
                return_document=ReturnDocument.AFTER,
            )
            if document is None:
                document = self.collection.find_one({
                    "public_id": identifier, "user_id": str(user_id), "deleted": {"$ne": True},
                })
            return self._record(document)
        except (ValueError, TypeError) as exc:
            raise EntityNotFoundError("Notification was not found.") from exc
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not update the notification.") from exc
