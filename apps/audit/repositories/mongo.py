"""MongoDB append-only audit log adapter."""
from datetime import datetime, timezone
from uuid import uuid4

from pymongo import DESCENDING
from pymongo.errors import PyMongoError

from infrastructure.database.exceptions import DatabaseConnectionError
from infrastructure.database.mongodb import get_mongo_database


class MongoAuditLogRepository:
    collection_name = "audit_logs"

    def __init__(self, database=None):
        self.collection = (database if database is not None else get_mongo_database())[self.collection_name]
        try:
            self.collection.create_index([("public_id", 1)], unique=True)
            self.collection.create_index([("created_at", DESCENDING), ("public_id", DESCENDING)])
            self.collection.create_index([("action", 1), ("created_at", DESCENDING)])
            self.collection.create_index([("object_type", 1), ("object_id", 1)])
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not initialize audit log indexes.") from exc

    def create(self, **values):
        actor_id = values.pop("actor_id", None)
        document = {
            "public_id": str(uuid4()),
            "actor_id": str(actor_id) if actor_id else None,
            "actor_email": values.pop("actor_email", ""),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "action": values.pop("action"),
            "object_type": values.pop("object_type", ""),
            "object_id": str(values.pop("object_id", "")),
            "object_repr": values.pop("object_repr", ""),
            "changes": values.pop("changes", {}) or {},
            "ip_address": values.pop("ip_address", None),
            "user_agent": values.pop("user_agent", ""),
            "extra": values.pop("extra", {}) or {},
        }
        if values:
            raise TypeError(f"Unsupported audit fields: {', '.join(sorted(values))}")
        try:
            self.collection.insert_one(document)
            return document
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not write the audit event.") from exc

    def list_recent(self, *, action=None, limit=150):
        query = {"action": action} if action else {}
        try:
            return [
                {key: value for key, value in row.items() if key != "_id"}
                | {"actor": {"email": row.get("actor_email", "")}}
                for row in self.collection.find(query).sort(
                    [("created_at", DESCENDING), ("public_id", DESCENDING)]
                ).limit(limit)
            ]
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not list audit events.") from exc

    def import_sql_record(self, record):
        """Idempotently preserve a legacy SQL audit event and its original timestamp."""
        actor = getattr(record, "actor", None)
        document = {
            "public_id": str(record.pk),
            "actor_id": str(record.actor_id) if record.actor_id else None,
            "actor_email": getattr(actor, "email", "") if actor else "",
            "action": record.action,
            "object_type": record.object_type,
            "object_id": record.object_id,
            "object_repr": record.object_repr,
            "changes": record.changes or {},
            "ip_address": record.ip_address,
            "user_agent": record.user_agent,
            "extra": record.extra or {},
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }
        try:
            result = self.collection.update_one(
                {"public_id": document["public_id"]}, {"$setOnInsert": document}, upsert=True
            )
            return result.upserted_id is not None
        except PyMongoError as exc:
            raise DatabaseConnectionError("MongoDB could not import the SQL audit event.") from exc
