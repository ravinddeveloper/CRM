"""Capture catalog-affecting SQL changes in the course catalog outbox."""
import logging

from decouple import config
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models.signals import m2m_changed, post_save, pre_delete
from django.dispatch import receiver

from apps.accounts.models import Profile
from infrastructure.database.config import DatabaseEngine, get_database_engine

from .models import Category, Course, CourseCatalogSyncEvent, Tag

logger = logging.getLogger("apps.courses")
User = get_user_model()


def enqueue_course(course_id, event_type=CourseCatalogSyncEvent.UPSERT):
    enabled = config("MONGO_COURSE_CATALOG_SYNC_ENABLED", default=False, cast=bool)
    if get_database_engine() is not DatabaseEngine.MONGODB and not enabled:
        return
    event = CourseCatalogSyncEvent.objects.create(event_type=event_type, course_id=course_id)
    transaction.on_commit(lambda: _dispatch(event.pk))


def _dispatch(event_id):
    try:
        from .tasks import process_catalog_sync_event
        process_catalog_sync_event.delay(event_id)
    except Exception:
        logger.exception("Could not dispatch course catalog event %s; it remains queued.", event_id)


def _enqueue_courses(queryset):
    for course_id in queryset.values_list("pk", flat=True).iterator():
        enqueue_course(course_id)


@receiver(post_save, sender=Course, dispatch_uid="courses.mongo_catalog.course.save")
def course_saved(sender, instance, raw=False, **kwargs):
    if not raw:
        enqueue_course(instance.pk)


@receiver(pre_delete, sender=Course, dispatch_uid="courses.mongo_catalog.course.delete")
def course_deleted(sender, instance, **kwargs):
    enqueue_course(instance.pk, CourseCatalogSyncEvent.DELETE)


@receiver(post_save, sender=Category, dispatch_uid="courses.mongo_catalog.category.save")
@receiver(pre_delete, sender=Category, dispatch_uid="courses.mongo_catalog.category.delete")
def category_changed(sender, instance, **kwargs):
    _enqueue_courses(Course.objects.filter(category_id=instance.pk))


@receiver(post_save, sender=Tag, dispatch_uid="courses.mongo_catalog.tag.save")
@receiver(pre_delete, sender=Tag, dispatch_uid="courses.mongo_catalog.tag.delete")
def tag_changed(sender, instance, **kwargs):
    _enqueue_courses(instance.courses.all())


@receiver(m2m_changed, sender=Course.tags.through, dispatch_uid="courses.mongo_catalog.course.tags")
def course_tags_changed(sender, instance, action, reverse, pk_set, **kwargs):
    if action == "pre_clear":
        instance._mongo_sync_course_ids = tuple(
            instance.courses.values_list("pk", flat=True) if reverse else (instance.pk,)
        )
        return
    if action == "post_clear":
        for course_id in getattr(instance, "_mongo_sync_course_ids", ()):
            enqueue_course(course_id)
        return
    if not action.startswith("post_"):
        return
    if reverse:
        _enqueue_courses(Course.objects.filter(pk__in=pk_set or ()))
    else:
        enqueue_course(instance.pk)


@receiver(post_save, sender=User, dispatch_uid="courses.mongo_catalog.teacher.save")
@receiver(post_save, sender=Profile, dispatch_uid="courses.mongo_catalog.teacher.profile")
def teacher_changed(sender, instance, raw=False, **kwargs):
    if raw:
        return
    user_id = instance.pk if sender is User else instance.user_id
    _enqueue_courses(Course.objects.filter(teacher_id=user_id))
