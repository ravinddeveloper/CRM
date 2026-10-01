from datetime import datetime, timezone

import pytest
from django.contrib.auth.hashers import check_password

from apps.accounts.repository_service import AccountRepositoryService
from infrastructure.database.exceptions import ApplicationValidationError


class InMemoryAccountRepository:
    def __init__(self):
        self.records = {}

    def create(self, **fields):
        from apps.accounts.repositories.base import AccountRecord
        from uuid import uuid4

        record = AccountRecord(
            id=str(uuid4()), email=fields["email"], password_hash=fields["password_hash"],
            username=fields["username"], first_name=fields["first_name"], last_name=fields["last_name"],
            role=fields["role"], is_active=True, email_verified=False, date_joined=datetime.now(timezone.utc),
        )
        self.records[record.id] = record
        return record

    def get_by_id(self, account_id):
        return self.records[account_id]

    def update(self, account_id, changes):
        from dataclasses import replace

        self.records[account_id] = replace(self.records[account_id], **changes)
        return self.records[account_id]

    def delete(self, account_id):
        del self.records[account_id]

    def list(self, *, limit=100, offset=0):
        return list(self.records.values())[offset:offset + limit]


def test_account_service_applies_shared_crud_and_password_rules():
    repository = InMemoryAccountRepository()
    service = AccountRepositoryService(repository)
    account = service.create_user(email="  USER@example.com ", password="correct-horse", first_name="User")

    assert account.email == "user@example.com"
    assert account.username.startswith("account_")
    assert check_password("correct-horse", account.password_hash)
    assert service.get_user(account.id) == account
    assert service.update_user(account.id, {"first_name": "Updated"}).first_name == "Updated"
    assert service.list_users() == [service.get_user(account.id)]
    service.delete_user(account.id)
    assert service.list_users() == []


@pytest.mark.parametrize(
    "values",
    [
        {"email": "bad-email", "password": "valid-password"},
        {"email": "user@example.com", "password": "short"},
        {"email": "user@example.com", "password": "valid-password", "role": "root"},
    ],
)
def test_account_service_validation_is_backend_independent(values):
    service = AccountRepositoryService(InMemoryAccountRepository())
    with pytest.raises(ApplicationValidationError):
        service.create_user(**values)
