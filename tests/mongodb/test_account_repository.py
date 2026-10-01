import os
from uuid import uuid4

import pytest

MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    pytest.skip("Set MONGO_URI to run MongoDB integration tests.", allow_module_level=True)

pytest.importorskip("pymongo")
from pymongo import MongoClient

from apps.accounts.repositories.mongo import MongoAccountRepository
from infrastructure.database.exceptions import EntityNotFoundError

@pytest.fixture
def repository():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1500)
    database = client[f"test_eduflow_{uuid4().hex}"]
    try:
        yield MongoAccountRepository(database=database)
    finally:
        client.drop_database(database.name)
        client.close()


def test_create_retrieve_update_delete_account(repository):
    account = repository.create(
        email="mongo@example.com", password_hash="encoded-password", username="mongo-user",
        first_name="Mongo", last_name="User",
    )
    assert repository.get_by_id(account.id).email == "mongo@example.com"
    assert repository.update(account.id, {"first_name": "Updated"}).first_name == "Updated"
    repository.delete(account.id)
    with pytest.raises(EntityNotFoundError):
        repository.get_by_id(account.id)
