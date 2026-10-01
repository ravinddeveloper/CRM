from unittest.mock import patch

import pytest
from django.core.management import call_command, CommandError
from django.utils import timezone

from apps.accounts.models import AccountSyncEvent
from infrastructure.database.config import DatabaseEngine

pytestmark = pytest.mark.django_db


def test_sync_account_outbox_requires_mongo_engine():
    with patch(
        "apps.accounts.management.commands.sync_account_outbox.get_database_engine",
        return_value=DatabaseEngine.SQL,
    ):
        with pytest.raises(CommandError, match="Select DATABASE_ENGINE=mongodb"):
            call_command("sync_account_outbox")


def test_sync_account_outbox_drains_a_bounded_snapshot():
    event = AccountSyncEvent.objects.create(
        account_id="518f1675-19ba-46c0-9737-14a66da84fc8", event_type=AccountSyncEvent.UPSERT
    )

    def mark_processed(event_id):
        AccountSyncEvent.objects.filter(pk=event_id).update(processed_at=timezone.now())
        return True

    with (
        patch(
            "apps.accounts.management.commands.sync_account_outbox.get_database_engine",
            return_value=DatabaseEngine.MONGODB,
        ),
        patch("apps.accounts.management.commands.sync_account_outbox.process_event", side_effect=mark_processed) as process,
    ):
        call_command("sync_account_outbox", "--batch-size", "1")

    process.assert_called_once_with(event.pk)
