from unittest.mock import patch

import pytest

from apps.enrollments.models import EnrollmentStatus, EnrollmentSyncEvent
from infrastructure.database.config import DatabaseEngine
from tests.factories import make_course, make_enrollment, make_student

pytestmark = pytest.mark.django_db


def test_mongodb_mode_enqueues_enrollment_state_changes_and_delete():
    student = make_student()
    course = make_course(status="published")
    with patch("apps.enrollments.signals.get_database_engine", return_value=DatabaseEngine.MONGODB):
        enrollment = make_enrollment(user=student, course=course)
        enrollment_id = str(enrollment.pk)
        enrollment.status = EnrollmentStatus.SUSPENDED
        enrollment.save(update_fields=["status"])
        enrollment.delete()

    events = list(EnrollmentSyncEvent.objects.order_by("id"))
    assert [event.event_type for event in events] == ["upsert", "upsert", "delete"]
    assert events[0].payload["public_id"] == enrollment_id
    assert events[1].payload["status"] == EnrollmentStatus.SUSPENDED
    assert events[2].payload == {}


def test_sql_mode_does_not_create_mongo_outbox_events():
    with patch("apps.enrollments.signals.get_database_engine", return_value=DatabaseEngine.SQL):
        make_enrollment(user=make_student(), course=make_course(status="published"))

    assert EnrollmentSyncEvent.objects.count() == 0


def test_sync_task_projects_latest_committed_enrollment_state():
    from apps.enrollments.tasks import process_event

    with patch("apps.enrollments.signals.get_database_engine", return_value=DatabaseEngine.MONGODB):
        enrollment = make_enrollment(user=make_student(), course=make_course(status="published"))
    event = EnrollmentSyncEvent.objects.filter(enrollment_id=enrollment.pk).order_by("id").first()
    enrollment.status = EnrollmentStatus.SUSPENDED
    enrollment.save(update_fields=["status"])

    with patch("apps.enrollments.tasks.MongoEnrollmentRepository") as repository_type:
        process_event(event.pk)

    repository_type.return_value.sync_sql_record.assert_called_once_with(
        repository_type.return_value.sync_sql_record.call_args.args[0], source_revision=event.pk
    )
    projected = repository_type.return_value.sync_sql_record.call_args.args[0]
    assert projected.status == EnrollmentStatus.SUSPENDED
    event.refresh_from_db()
    assert event.processed_at is not None
    assert event.attempts == 0


def test_stale_upsert_event_does_not_resurrect_deleted_enrollment():
    from apps.enrollments.tasks import process_event

    with patch("apps.enrollments.signals.get_database_engine", return_value=DatabaseEngine.MONGODB):
        enrollment = make_enrollment(user=make_student(), course=make_course(status="published"))
        event = EnrollmentSyncEvent.objects.filter(enrollment_id=enrollment.pk).order_by("id").first()
        enrollment.delete()

    with patch("apps.enrollments.tasks.MongoEnrollmentRepository") as repository_type:
        process_event(event.pk)

    repository_type.return_value.delete_by_id.assert_called_once_with(
        event.enrollment_id, source_revision=event.pk
    )
    event.refresh_from_db()
    assert event.processed_at is not None


def test_periodic_drain_recovers_pending_outbox_rows():
    from apps.enrollments.tasks import drain_pending_enrollment_sync_events

    with patch("apps.enrollments.signals.get_database_engine", return_value=DatabaseEngine.MONGODB):
        enrollment = make_enrollment(user=make_student(), course=make_course(status="published"))
    event = EnrollmentSyncEvent.objects.get(enrollment_id=enrollment.pk)

    with (
        patch("apps.enrollments.tasks.get_database_engine", return_value=DatabaseEngine.MONGODB),
        patch("apps.enrollments.tasks.MongoEnrollmentRepository") as repository_type,
    ):
        processed = drain_pending_enrollment_sync_events.run(batch_size=10)

    assert processed == 1
    repository_type.return_value.sync_sql_record.assert_called_once()
    event.refresh_from_db()
    assert event.processed_at is not None
