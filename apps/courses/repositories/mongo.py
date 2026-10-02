"""MongoDB read adapter for the synchronized published course catalog."""
import re
from datetime import timezone
from decimal import Decimal
from uuid import UUID

from bson.decimal128 import Decimal128
from pymongo import DESCENDING
from pymongo.errors import PyMongoError

from infrastructure.database.exceptions import DatabaseConnectionError
from infrastructure.database.mongodb import get_mongo_database


class MongoCourseCatalogRepository:
    collection_name = "course_catalog"

    def __init__(self, database=None):
        database = database if database is not None else get_mongo_database()
        self.collection = database[self.collection_name]
        self.category_collection = database["course_categories"]
        try:
            self.collection.create_index([("status", 1), ("created_at", DESCENDING)])
            self.collection.create_index([("category.slug", 1), ("status", 1)])
            self.collection.create_index([("status", 1), ("price", 1)])
            self.collection.create_index([("status", 1), ("enrollment_count", DESCENDING)])
            self.collection.create_index([("status", 1), ("average_rating", DESCENDING)])
            self.collection.create_index([("public_id", 1)], unique=True)
            self.category_collection.create_index([("public_id", 1)], unique=True)
            self.category_collection.create_index([("is_active", 1), ("order", 1), ("name", 1)])
            self.category_collection.create_index(
                [("slug", 1)], unique=True, partialFilterExpression={"deleted": False}
            )
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not initialize course catalog indexes.") from exc

    @staticmethod
    def _record(document):
        result = {key: value for key, value in document.items() if key not in {"_id", "deleted", "source_revision"}}
        for key in ("price", "discount_price", "effective_price", "average_rating"):
            if result.get(key) is not None:
                value = result[key]
                result[key] = value.to_decimal() if isinstance(value, Decimal128) else Decimal(str(value))
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
        sections = []
        for section in course.sections.all().order_by("order"):
            lectures = [
                {
                    "id": str(lec.pk), "title": lec.title, "order": lec.order,
                    "estimated_duration": lec.estimated_duration,
                    "duration_seconds": lec.estimated_duration,
                    "is_free_preview": lec.is_free_preview,
                    "is_published": lec.is_published,
                }
                for lec in section.lectures.all().order_by("order")
            ]
            sections.append({
                "id": str(section.pk), "title": section.title, "order": section.order,
                "is_published": section.is_published,
                "lecture_count": len(lectures),
                "lectures": lectures,
            })
        return {
            "public_id": str(course.pk), "id": str(course.pk), "title": course.title,
            "slug": course.slug, "short_description": course.short_description,
            "description": course.description,
            "thumbnail": course.thumbnail.name if course.thumbnail else None,
            "category": ({"id": str(category.pk), "name": category.name, "slug": category.slug,
                          "description": category.description, "icon": category.icon} if category else None),
            "teacher_name": course.teacher.full_name,
            "teacher_first_name": course.teacher.first_name, "teacher_email": course.teacher.email,
            "teacher_last_name": course.teacher.last_name,
            "teacher_id": str(course.teacher_id),
            "teacher": {
                "full_name": course.teacher.full_name,
                "first_name": course.teacher.first_name,
                "email": course.teacher.email,
                "profile": {"bio": getattr(getattr(course.teacher, "profile", None), "bio", "")},
            },
            "price": Decimal128(str(course.price)),
            "discount_price": Decimal128(str(course.discount_price)) if course.discount_price is not None else None,
            "effective_price": Decimal128(str(effective_price)), "currency": course.currency,
            "is_free": course.is_free, "status": course.status, "is_featured": course.is_featured,
            "is_published": course.is_published,
            "discount_percentage": course.discount_percentage,
            "difficulty": course.difficulty, "estimated_duration": course.estimated_duration,
            "enrollment_count": course.enrollment_count, "average_rating": Decimal128(str(course.average_rating)),
            "description": course.description, "preview_video_key": course.preview_video_key,
            "language": course.language,
            "learning_objectives": list(course.learning_objectives) if course.learning_objectives else [],
            "requirements": list(course.requirements) if course.requirements else [],
            "updated_at": course.updated_at,
            "total_lectures_count": sum(s["lecture_count"] for s in sections),
            "tags": [{"id": str(tag.pk), "name": tag.name, "slug": tag.slug} for tag in course.tags.all()],
            "sections": sections,
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

    def list_published(self, *, category=None, search="", difficulty=None, is_free=None,
                       price_min=None, price_max=None, sort="newest", featured_only=False,
                       include_related_search=False,
                       limit=20, offset=0):
        query = {"status": "published", "deleted": {"$ne": True}}
        if category:
            query["category.slug"] = category
        if difficulty:
            query["difficulty"] = difficulty
        if is_free is not None:
            query["is_free"] = is_free
        if price_min:
            query["price"] = {"$gte": Decimal128(str(price_min))}
        if price_max:
            query.setdefault("price", {})["$lte"] = Decimal128(str(price_max))
        if featured_only:
            query["is_featured"] = True
        if search:
            pattern = re.escape(search)
            search_fields = ["title", "short_description", "description"]
            if include_related_search:
                search_fields.extend(["teacher_first_name", "teacher_last_name", "tags.name"])
            query["$or"] = [
                {field: {"$regex": pattern, "$options": "i"}}
                for field in search_fields
            ]
        try:
            count = self.collection.count_documents(query)
            sort_fields = {
                "newest": [("created_at", DESCENDING), ("public_id", DESCENDING)],
                "popular": [("enrollment_count", DESCENDING), ("public_id", DESCENDING)],
                "rating": [("average_rating", DESCENDING), ("public_id", DESCENDING)],
                "price_low": [("price", 1), ("public_id", 1)],
                "price_high": [("price", DESCENDING), ("public_id", DESCENDING)],
            }
            rows = self.collection.find(query).sort(sort_fields.get(sort, sort_fields["newest"])).skip(offset).limit(limit)
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

    def get_by_slug(self, slug):
        try:
            document = self.collection.find_one({"slug": slug, "deleted": {"$ne": True}})
            return self._record(document) if document else None
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not retrieve the course catalog record.") from exc

    @staticmethod
    def _category_document(category):
        return {
            "public_id": str(category.pk), "id": str(category.pk), "name": category.name,
            "slug": category.slug, "description": category.description, "icon": category.icon,
            "image": category.image.name if category.image else None,
            "is_active": category.is_active, "order": category.order,
            "parent_id": str(category.parent_id) if category.parent_id else None,
            "deleted": False,
        }

    @staticmethod
    def _category_record(document):
        return {
            key: value for key, value in document.items()
            if key not in {"_id", "public_id", "deleted", "source_revision"}
        }

    def import_sql_category(self, category):
        document = self._category_document(category)
        try:
            result = self.category_collection.update_one(
                {"public_id": document["public_id"]}, {"$setOnInsert": document}, upsert=True
            )
            return result.upserted_id is not None
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not import the SQL course category.") from exc

    def sync_sql_category(self, category, *, source_revision):
        document = self._category_document(category)
        try:
            self.category_collection.update_one(
                {"public_id": document["public_id"]},
                [{"$replaceWith": {"$cond": [
                    {"$gt": [source_revision, {"$ifNull": ["$source_revision", -1]}]},
                    {"$mergeObjects": ["$$ROOT", {**document, "source_revision": source_revision}]},
                    "$$ROOT",
                ]}}],
                upsert=True,
            )
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not synchronize the SQL course category.") from exc

    def delete_category_by_id(self, category_id, *, source_revision):
        identifier = str(category_id)
        try:
            self.category_collection.update_one(
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
            raise DatabaseConnectionError("MongoDB could not tombstone the SQL course category.") from exc

    def list_categories(self, *, root_only=False):
        query = {"is_active": True, "deleted": {"$ne": True}}
        if root_only:
            query["parent_id"] = None
        try:
            return [self._category_record(document) for document in self.category_collection.find(query).sort(
                [("order", 1), ("name", 1)]
            )]
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not list course categories.") from exc

    def get_category_by_slug(self, slug):
        try:
            document = self.category_collection.find_one({
                "slug": slug, "is_active": True, "deleted": {"$ne": True},
            })
            return self._category_record(document) if document else None
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not retrieve the course category.") from exc
