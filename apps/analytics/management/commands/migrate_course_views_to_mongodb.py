"""Idempotently copy legacy SQL course-view events into MongoDB."""
from django.core.management.base import BaseCommand, CommandError

from apps.analytics.models import CourseView
from apps.analytics.repositories.mongo import MongoCourseViewRepository
from apps.courses.models import Course
from infrastructure.database.config import DatabaseEngine, get_database_engine


class Command(BaseCommand):
    help = "Copy SQL course-view history to MongoDB before changing the analytics repository engine."

    def handle(self, *args, **options):
        if get_database_engine() is not DatabaseEngine.SQL:
            raise CommandError("Run this command with DATABASE_ENGINE=sql so course-view rows come from SQL.")

        repository = MongoCourseViewRepository()
        count = 0
        for view in CourseView.objects.order_by("created_at", "id").iterator(chunk_size=1000):
            if repository.import_sql_record(view):
                count += 1
        course_count = 0
        for course in Course.objects.only("pk", "total_views").iterator(chunk_size=1000):
            repository.import_sql_course_count(course_id=course.pk, total_views=course.total_views)
            course_count += 1
        self.stdout.write(self.style.SUCCESS(
            f"Imported {count} course-view records and {course_count} legacy course counters into MongoDB."
        ))
