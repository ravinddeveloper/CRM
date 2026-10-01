"""MongoDB adapter for append-only course view events."""
from datetime import datetime, timezone
from uuid import uuid4

from pymongo import ASCENDING, DESCENDING
from pymongo.errors import PyMongoError

from apps.analytics.repositories.base import CourseViewRecord
from infrastructure.database.exceptions import DatabaseConnectionError
from infrastructure.database.mongodb import get_mongo_database


class MongoCourseViewRepository:
    """Stores events as Mongo documents with scalar relationship identifiers."""
    collection_name = "course_views"
    counter_collection_name = "course_view_counts"

    def __init__(self, database=None):
        self.collection = (database if database is not None else get_mongo_database())[self.collection_name]
        self.counter_collection = self.collection.database[self.counter_collection_name]
        try:
            self.collection.create_index([("course_id", ASCENDING), ("created_at", DESCENDING)])
            self.collection.create_index([("course_id", ASCENDING), ("counts_toward_total", ASCENDING)])
            self.collection.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)], sparse=True)
            self.collection.create_index([("public_id", ASCENDING)], unique=True)
            self.counter_collection.create_index([("course_id", ASCENDING)], unique=True)
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not initialize course view indexes.") from exc

    def record_view(self, *, course_id, user_id, ip_address, session_key):
        document = {
            "public_id": str(uuid4()),
            "course_id": str(course_id),
            "user_id": str(user_id) if user_id else None,
            "ip_address": ip_address,
            "session_key": session_key,
            "created_at": datetime.now(timezone.utc),
            "counts_toward_total": True,
        }
        try:
            self.collection.insert_one(document)
            return CourseViewRecord(
                id=document["public_id"], course_id=document["course_id"], user_id=document["user_id"],
                ip_address=document["ip_address"], session_key=document["session_key"],
                created_at=document["created_at"],
            )
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not record the course view.") from exc

    def import_sql_record(self, view):
        """Idempotently copy a legacy SQL event while retaining IDs and time."""
        document = {
            "public_id": str(view.pk),
            "course_id": str(view.course_id),
            "user_id": str(view.user_id) if view.user_id else None,
            "ip_address": view.ip_address,
            "session_key": view.session_key,
            "created_at": view.created_at,
            "counts_toward_total": False,
        }
        try:
            result = self.collection.update_one(
                {"public_id": document["public_id"]}, {"$setOnInsert": document}, upsert=True
            )
            return result.upserted_id is not None
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not import the SQL course view.") from exc

    def import_sql_course_count(self, *, course_id, total_views):
        """Seed the pre-existing course counter without overwriting later Mongo events."""
        try:
            self.counter_collection.update_one(
                {"course_id": str(course_id)},
                {"$setOnInsert": {
                    "course_id": str(course_id),
                    "legacy_total_views": int(total_views),
                }},
                upsert=True,
            )
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not import the SQL course view count.") from exc

    def get_total_views(self, *, course_id):
        try:
            counter = self.counter_collection.find_one({"course_id": str(course_id)}) or {}
            legacy_total = int(counter.get("legacy_total_views", 0))
            new_views = self.collection.count_documents({
                "course_id": str(course_id), "counts_toward_total": True,
            })
            return legacy_total + new_views
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not read the course view count.") from exc
