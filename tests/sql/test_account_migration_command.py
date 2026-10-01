from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

pytestmark = pytest.mark.django_db


def test_account_migration_dry_run_does_not_connect_to_mongodb(capsys):
    get_user_model().objects.create_user(email="snapshot@example.com", password="secret")

    with patch("apps.accounts.management.commands.migrate_accounts_to_mongodb.MongoAccountRepository") as repo:
        call_command("migrate_accounts_to_mongodb", "--dry-run")

    repo.assert_not_called()
    assert "1 SQL accounts" in capsys.readouterr().out


def test_account_migration_imports_existing_rows_and_reports_resumable_records(capsys):
    User = get_user_model()
    User.objects.create_user(email="first@example.com", username="first", password="secret")
    User.objects.create_user(email="second@example.com", username="second", password="secret")
    imported_ids = []

    class FakeRepository:
        def import_sql_record(self, user):
            imported_ids.append(str(user.pk))
            return len(imported_ids) == 1

    with patch(
        "apps.accounts.management.commands.migrate_accounts_to_mongodb.MongoAccountRepository",
        return_value=FakeRepository(),
    ):
        call_command("migrate_accounts_to_mongodb", "--batch-size", "1")

    assert len(imported_ids) == 2
    output = capsys.readouterr().out
    assert "1 imported, 1 already present" in output
    assert "SQL remains authoritative" in output
