"""MongoDB read adapter for the synchronized published course catalog."""
import re
from datetime import timezone

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
        result["created_at"] = result["created_at"].replace(tzinfo=timezone.utc) if result["created_at"].tzinfo is None else result["created_at"]
        return result

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
