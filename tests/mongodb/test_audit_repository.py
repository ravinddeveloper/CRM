import os
from uuid import uuid4

import pytest

MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    pytest.skip("Set MONGO_URI to run MongoDB integration tests.", allow_module_level=True)

pytest.importorskip("pymongo")
from pymongo import MongoClient

from apps.audit.repositories.mongo import MongoAuditLogRepository


@pytest.fixture
def repository():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1500)
    database = client[f"test_audit_{uuid4().hex}"]
    try:
        yield MongoAuditLogRepository(database=database)
    finally:
        client.drop_database(database.name)
        client.close()


def test_audit_events_round_trip_with_scalar_actor_and_filtering(repository):
    record = repository.create(
        actor_id="user-uuid", actor_email="admin@example.test", action="role_changed",
        object_type="User", object_id="user-uuid", object_repr="admin@example.test",
        changes={"from": "student", "to": "teacher"}, ip_address="192.0.2.8",
    )

    logs = repository.list_recent(action="role_changed", limit=10)

    assert logs[0]["public_id"] == record["public_id"]
    assert logs[0]["actor"]["email"] == "admin@example.test"
    assert logs[0]["changes"]["to"] == "teacher"


def test_legacy_audit_import_preserves_id_and_timestamp_and_is_idempotent(repository):
    from datetime import datetime, timezone
    from types import SimpleNamespace

    timestamp = datetime(2025, 1, 2, tzinfo=timezone.utc)
    record = SimpleNamespace(
        pk="audit-uuid", actor_id="user-uuid", actor=SimpleNamespace(email="admin@example.test"),
        action="user_login", object_type="User", object_id="user-uuid", object_repr="admin",
        changes={}, ip_address=None, user_agent="", extra={}, created_at=timestamp, updated_at=timestamp,
    )

    assert repository.import_sql_record(record) is True
    assert repository.import_sql_record(record) is False
    imported = repository.collection.find_one({"public_id": "audit-uuid"})
    assert imported["created_at"] == timestamp
