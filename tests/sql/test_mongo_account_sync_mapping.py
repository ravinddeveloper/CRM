import pytest
from django.contrib.auth import get_user_model

from apps.accounts.repositories.mongo import MongoAccountRepository

pytestmark = pytest.mark.django_db


class FakeCollection:
    def __init__(self):
        self.updates = []

    def create_index(self, *args, **kwargs):
        return None

    def update_one(self, query, update, **kwargs):
        self.updates.append((query, update, kwargs))
        return type("Result", (), {"upserted_id": "created"})()


class FakeDatabase:
    def __init__(self):
        self.accounts = FakeCollection()

    def __getitem__(self, name):
        assert name == "accounts"
        return self.accounts


def test_mongo_account_sync_uses_monotonic_revisions_and_complete_sql_snapshot():
    user = get_user_model().objects.create_user(
        email="projection@example.com", username="projection-user", password="secret"
    )
    user.profile.bio = "Profile snapshot"
    user.profile.save()
    database = FakeDatabase()
    repository = MongoAccountRepository(database=database)

    repository.import_sql_record(user, source_revision=37)

    query, update, kwargs = database.accounts.updates[-1]
    assert query == {"public_id": str(user.pk)}
    assert kwargs["upsert"] is True
    condition = update[0]["$replaceWith"]["$cond"]
    assert condition[0] == {"$gt": [37, {"$ifNull": ["$source_revision", -1]}]}
    document = condition[1]["$mergeObjects"][1]
    assert document["password_hash"] == user.password
    assert document["profile"]["bio"] == "Profile snapshot"
    assert document["source_revision"] == 37
    assert document["deleted"] is False


def test_mongo_account_delete_writes_revisioned_tombstone():
    database = FakeDatabase()
    repository = MongoAccountRepository(database=database)
    account_id = "518f1675-19ba-46c0-9737-14a66da84fc8"

    repository.delete_by_id(account_id, source_revision=42)

    query, update, kwargs = database.accounts.updates[-1]
    assert query == {"public_id": account_id}
    assert kwargs["upsert"] is True
    condition = update[0]["$replaceWith"]["$cond"]
    assert condition[0] == {"$gt": [42, {"$ifNull": ["$source_revision", -1]}]}
    tombstone = condition[1]["$mergeObjects"][1]
    assert tombstone == {"public_id": account_id, "deleted": True, "source_revision": 42}
