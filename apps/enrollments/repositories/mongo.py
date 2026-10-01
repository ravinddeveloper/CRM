"""MongoDB adapter for student enrollment listings."""
from datetime import timezone

from pymongo import ASCENDING, DESCENDING
from pymongo.errors import PyMongoError

from infrastructure.database.exceptions import DatabaseConnectionError
from infrastructure.database.mongodb import get_mongo_database

from .base import EnrollmentRecord


class MongoEnrollmentRepository:
    collection_name = "enrollments"

    def __init__(self, database=None):
        self.collection = (database if database is not None else get_mongo_database())[self.collection_name]
        try:
            self.collection.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
            self.collection.create_index([("public_id", ASCENDING)], unique=True)
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not initialize enrollment indexes.") from exc

    @staticmethod
    def _record(document):
        expires_at = document.get("expires_at")
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        created_at = document["created_at"]
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return EnrollmentRecord(
            id=document["public_id"], user_id=document["user_id"], course_id=document["course_id"],
            status=document["status"], access_type=document["access_type"],
            expires_at=expires_at, created_at=created_at,
        )

    def import_sql_record(self, enrollment):
        """Idempotently copy an SQL enrollment while retaining its public ID."""
        document = {
            "public_id": str(enrollment.pk), "user_id": str(enrollment.user_id),
            "course_id": str(enrollment.course_id), "status": enrollment.status,
            "access_type": enrollment.access_type, "expires_at": enrollment.expires_at,
            "created_at": enrollment.created_at, "deleted": False, "source_revision": 0,
        }
        try:
            result = self.collection.update_one(
                {"public_id": document["public_id"]}, {"$setOnInsert": document}, upsert=True
            )
            return result.upserted_id is not None
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not import the SQL enrollment.") from exc

    def sync_sql_record(self, enrollment, *, source_revision):
        """Upsert the current committed SQL state into the Mongo read model."""
        document = {
            "public_id": str(enrollment.pk), "user_id": str(enrollment.user_id),
            "course_id": str(enrollment.course_id), "status": enrollment.status,
            "access_type": enrollment.access_type, "expires_at": enrollment.expires_at,
            "created_at": enrollment.created_at, "deleted": False,
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
            raise DatabaseConnectionError("MongoDB could not synchronize the SQL enrollment.") from exc

    def delete_by_id(self, enrollment_id, *, source_revision):
        try:
            identifier = str(enrollment_id)
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
            raise DatabaseConnectionError("MongoDB could not remove the SQL enrollment.") from exc

    def list_for_user(self, *, user_id, limit, offset):
        if limit < 1 or offset < 0:
            return 0, []
        try:
            query = {"user_id": str(user_id), "deleted": {"$ne": True}}
            count = self.collection.count_documents(query)
            docs = self.collection.find(query).sort(
                [("created_at", DESCENDING), ("public_id", DESCENDING)]
            ).skip(offset).limit(limit)
            return count, [self._record(document) for document in docs]
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not list enrollments.") from exc
