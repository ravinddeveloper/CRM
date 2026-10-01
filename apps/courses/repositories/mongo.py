"""MongoDB read adapter for the synchronized published course catalog."""
import re
from datetime import timezone
from uuid import UUID

from pymongo import DESCENDING
from pymongo.errors import PyMongoError

from infrastructure.database.exceptions import DatabaseConnectionError
from infrastructure.database.mongodb import get_mongo_database


class MongoCourseCatalogRepository:
    collection_name = "course_catalog"

    def __init__(self, database=None):
        self.collection = (database if database is not None else get_mongo_database())[self.collection_name]
        try:
            self.collection.create_index([("status", 1), ("created_at", DESCENDING)])
            self.collection.create_index([("category.slug", 1), ("status", 1)])
            self.collection.create_index([("public_id", 1)], unique=True)
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not initialize course catalog indexes.") from exc

    @staticmethod
    def _record(document):
        result = {key: value for key, value in document.items() if key not in {"_id", "deleted", "source_revision"}}
        for key in ("price", "discount_price", "effective_price"):
            if result.get(key) is not None:
                result[key] = str(result[key])
        for field in ("created_at", "updated_at"):
            value = result.get(field)
            if value is not None and value.tzinfo is None:
                result[field] = value.replace(tzinfo=timezone.utc)
        return result

    @staticmethod
    def _sql_document(course):
        category = course.category
        effective_price = 0 if course.is_free else (
            course.discount_price if course.discount_price is not None else course.price
        )
        return {
            "public_id": str(course.pk), "id": str(course.pk), "title": course.title,
            "slug": course.slug, "short_description": course.short_description,
            "description": course.description,
            "thumbnail": course.thumbnail.name if course.thumbnail else None,
            "category": ({"id": str(category.pk), "name": category.name, "slug": category.slug,
                          "description": category.description, "icon": category.icon} if category else None),
            "teacher_name": course.teacher.full_name,
            "teacher_id": str(course.teacher_id),
            "teacher": {
                "full_name": course.teacher.full_name,
                "profile": {"bio": getattr(getattr(course.teacher, "profile", None), "bio", "")},
            },
            "price": str(course.price), "discount_price": str(course.discount_price) if course.discount_price is not None else None,
            "effective_price": str(effective_price), "currency": course.currency,
            "is_free": course.is_free, "status": course.status, "is_featured": course.is_featured,
            "difficulty": course.difficulty, "estimated_duration": course.estimated_duration,
            "description": course.description, "preview_video_key": course.preview_video_key,
            "language": course.language, "learning_objectives": course.learning_objectives,
            "requirements": course.requirements, "updated_at": course.updated_at,
            "tags": [{"id": str(tag.pk), "name": tag.name, "slug": tag.slug} for tag in course.tags.all()],
            "sections": [{
                "id": str(section.pk), "title": section.title, "order": section.order,
                "lectures": [{
                    "id": str(lecture.pk), "title": lecture.title, "order": lecture.order,
                    "estimated_duration": lecture.estimated_duration,
                    "duration_seconds": lecture.estimated_duration,
                    "is_free_preview": lecture.is_free_preview,
                } for lecture in section.lectures.all()],
            } for section in course.sections.all()],
            "created_at": course.created_at, "deleted": False,
        }

    def import_sql_course(self, course):
        """Idempotently seed a catalog projection without replacing live state."""
        document = self._sql_document(course)
        try:
            result = self.collection.update_one(
                {"public_id": document["public_id"]}, {"$setOnInsert": document}, upsert=True
            )
            return result.upserted_id is not None
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not import the SQL course catalog row.") from exc

    def sync_sql_course(self, course, *, source_revision):
        """Apply a committed SQL snapshot only when its outbox revision is newer."""
        document = self._sql_document(course)
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
            raise DatabaseConnectionError("MongoDB could not synchronize the SQL course catalog row.") from exc

    def delete_by_id(self, course_id, *, source_revision):
        identifier = str(course_id)
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
            raise DatabaseConnectionError("MongoDB could not tombstone the SQL course catalog row.") from exc

    def list_published(self, *, category=None, search="", difficulty=None, is_free=None, limit=20, offset=0):
        query = {"status": "published", "deleted": {"$ne": True}}
        if category:
            query["category.slug"] = category
        if difficulty:
            query["difficulty"] = difficulty
        if is_free is not None:
            query["is_free"] = is_free
        if search:
            pattern = re.escape(search)
            query["$or"] = [
                {field: {"$regex": pattern, "$options": "i"}}
                for field in ("title", "short_description", "description")
            ]
        try:
            count = self.collection.count_documents(query)
            rows = self.collection.find(query).sort([("created_at", DESCENDING), ("public_id", DESCENDING)]).skip(offset).limit(limit)
            return count, [self._record(row) for row in rows]
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not list published courses.") from exc

    def get_by_id(self, course_id):
        try:
            identifier = str(UUID(str(course_id)))
            document = self.collection.find_one({"public_id": identifier, "deleted": {"$ne": True}})
            return self._record(document) if document else None
        except (ValueError, TypeError):
            return None
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not retrieve the course catalog record.") from exc
