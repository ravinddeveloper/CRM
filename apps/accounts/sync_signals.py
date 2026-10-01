"""Capture SQL identity changes in a transactional Mongo projection outbox."""
import logging

from decouple import config
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models.signals import m2m_changed, post_save, pre_delete
from django.dispatch import receiver

from infrastructure.database.config import DatabaseEngine, get_database_engine

from .models import AccountSyncEvent, EmailVerificationToken, PasswordResetToken, Profile

logger = logging.getLogger("apps.accounts")
User = get_user_model()


def _dispatch(event_id):
    try:
        from .tasks import process_account_sync_event
        process_account_sync_event.delay(event_id)
    except Exception:
        logger.exception("Could not dispatch account sync event %s; it remains queued.", event_id)


def enqueue_account(account_id, event_type=AccountSyncEvent.UPSERT):
    enabled = config("MONGO_ACCOUNT_SYNC_ENABLED", default=False, cast=bool)
    if get_database_engine() is not DatabaseEngine.MONGODB and not enabled:
        return
    event = AccountSyncEvent.objects.create(event_type=event_type, account_id=account_id)
    transaction.on_commit(lambda: _dispatch(event.pk))


@receiver(post_save, sender=User, dispatch_uid="accounts.mongo_outbox.user.save")
def user_saved(sender, instance, raw=False, **kwargs):
    if not raw:
        enqueue_account(instance.pk)


@receiver(pre_delete, sender=User, dispatch_uid="accounts.mongo_outbox.user.delete")
def user_deleted(sender, instance, **kwargs):
    enqueue_account(instance.pk, AccountSyncEvent.DELETE)


@receiver(post_save, sender=Profile, dispatch_uid="accounts.mongo_outbox.profile.save")
def profile_saved(sender, instance, raw=False, **kwargs):
    if not raw:
        enqueue_account(instance.user_id)


@receiver(post_save, sender=EmailVerificationToken, dispatch_uid="accounts.mongo_outbox.verify.save")
@receiver(post_save, sender=PasswordResetToken, dispatch_uid="accounts.mongo_outbox.reset.save")
def token_saved(sender, instance, raw=False, **kwargs):
    if not raw:
        enqueue_account(instance.user_id)


@receiver(m2m_changed, sender=User.groups.through, dispatch_uid="accounts.mongo_outbox.user.groups")
@receiver(m2m_changed, sender=User.user_permissions.through, dispatch_uid="accounts.mongo_outbox.user.permissions")
def user_grants_changed(sender, instance, action, reverse, pk_set, **kwargs):
    if action == "pre_clear":
        if reverse:
            lookup = "groups__pk" if sender is User.groups.through else "user_permissions__pk"
            instance._mongo_sync_user_ids = tuple(
                User.objects.filter(**{lookup: instance.pk}).values_list("pk", flat=True).distinct()
            )
        else:
            instance._mongo_sync_user_ids = (instance.pk,)
        return
    if action == "post_clear":
        for user_id in getattr(instance, "_mongo_sync_user_ids", ()):
            enqueue_account(user_id)
        return
    if not action.startswith("post_"):
        return
    if reverse:
        for user_id in pk_set or ():
            enqueue_account(user_id)
    else:
        enqueue_account(instance.pk)


@receiver(m2m_changed, sender=Group.permissions.through, dispatch_uid="accounts.mongo_outbox.group.permissions")
def group_permissions_changed(sender, instance, action, reverse, pk_set, **kwargs):
    if action == "pre_clear":
        group_ids = (
            Group.objects.filter(permissions__pk=instance.pk).values_list("pk", flat=True)
            if reverse else (instance.pk,)
        )
        instance._mongo_sync_user_ids = tuple(
            User.objects.filter(groups__pk__in=group_ids).values_list("pk", flat=True).distinct()
        )
        return
    if action == "post_clear":
        for user_id in getattr(instance, "_mongo_sync_user_ids", ()):
            enqueue_account(user_id)
        return
    if not action.startswith("post_"):
        return
    group_ids = (instance.pk,) if not reverse else (pk_set or ())
    for group_id in group_ids:
        for user_id in User.objects.filter(groups__pk=group_id).values_list("pk", flat=True).distinct().iterator():
            enqueue_account(user_id)


@receiver(post_save, sender=Group, dispatch_uid="accounts.mongo_outbox.group.save")
@receiver(pre_delete, sender=Group, dispatch_uid="accounts.mongo_outbox.group.delete")
def group_saved(sender, instance, **kwargs):
    for user_id in User.objects.filter(groups__pk=instance.pk).values_list("pk", flat=True).distinct().iterator():
        enqueue_account(user_id)
