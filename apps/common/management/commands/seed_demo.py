"""Management command to populate realistic demo data for development."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import UserRole
from apps.coupons.models import Coupon, DiscountType
from apps.courses.models import Category, Course, CourseStatus, DifficultyLevel, Section
from apps.lectures.models import (
    Lecture,
    LectureNote,
    LectureVideo,
    NoteType,
)

User = get_user_model()


class Command(BaseCommand):
    help = "Seed demo users, categories, courses, and lectures for local development."

    def handle(self, *args, **options):
        self.stdout.write("Starting EduFlow LMS demo data seeding...")

        # 1. Users (Admin, Teacher, Student)
        admin, _ = User.objects.get_or_create(
            email="admin@eduflow.local",
            defaults={
                "username": "admin",
                "first_name": "System",
                "last_name": "Admin",
                "role": UserRole.ADMIN,
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
                "email_verified": True,
            },
        )
        admin.set_password("Admin1234!")
        admin.save()
        self.stdout.write(self.style.SUCCESS("[OK] Admin user: admin@eduflow.local (Password: Admin1234!)"))

        teacher, _ = User.objects.get_or_create(
            email="teacher@eduflow.local",
            defaults={
                "username": "teacher_alex",
                "first_name": "Alex",
                "last_name": "Rivera",
                "role": UserRole.TEACHER,
                "is_active": True,
                "email_verified": True,
            },
        )
        teacher.set_password("Teacher1234!")
        teacher.save()
        self.stdout.write(self.style.SUCCESS("[OK] Teacher user: teacher@eduflow.local (Password: Teacher1234!)"))

        student, _ = User.objects.get_or_create(
            email="student@eduflow.local",
            defaults={
                "username": "student_jane",
                "first_name": "Jane",
                "last_name": "Doe",
                "role": UserRole.STUDENT,
                "is_active": True,
                "email_verified": True,
            },
        )
        student.set_password("Student1234!")
        student.save()
        self.stdout.write(self.style.SUCCESS("[OK] Student user: student@eduflow.local (Password: Student1234!)"))

        # 2. Categories
        cat_web, _ = Category.objects.get_or_create(
            slug="web-development",
            defaults={"name": "Web Development", "description": "Master full-stack web applications with Python & Django", "icon": "web"},
        )
        cat_data, _ = Category.objects.get_or_create(
            slug="data-science-ai",
            defaults={"name": "Data Science & AI", "description": "Machine learning, BigQuery, and neural networks", "icon": "ai"},
        )
        cat_cloud, _ = Category.objects.get_or_create(
            slug="cloud-devops",
            defaults={"name": "Cloud & DevOps", "description": "Docker, Kubernetes, CI/CD and production infrastructure", "icon": "cloud"},
        )
        self.stdout.write(self.style.SUCCESS("[OK] Created 3 Course Categories"))

        # 3. Demo Courses
        c1, _ = Course.objects.get_or_create(
            slug="complete-django-production-masterclass",
            defaults={
                "title": "Complete Django 5 & Production Masterclass",
                "teacher": teacher,
                "category": cat_web,
                "short_description": "Build modern, secure, full-stack web applications using Django, Redis, Celery, and Docker.",
                "description": "Comprehensive practical roadmap taking you from Django architectural fundamentals to deploying production-grade, highly available micro-services.",
                "price": Decimal("2999.00"),
                "discount_price": Decimal("1499.00"),
                "currency": "INR",
                "status": CourseStatus.PUBLISHED,
                "difficulty": DifficultyLevel.INTERMEDIATE,
                "is_featured": True,
                "is_bestseller": True,
                "estimated_duration": 480,
                "learning_objectives": [
                    "Design scalable database models and optimized ORM queries",
                    "Implement role-based authorization and session security",
                    "Integrate payment gateways with idempotent webhook handlers",
                    "Configure private S3/MinIO storage with expiring signed URLs",
                ],
                "requirements": [
                    "Basic knowledge of Python syntax",
                    "A computer with Docker and Python 3.12+ installed",
                ],
                "published_at": timezone.now(),
            },
        )

        c2, _ = Course.objects.get_or_create(
            slug="cloud-native-devops-with-docker-k8s",
            defaults={
                "title": "Cloud-Native DevOps with Docker & Kubernetes",
                "teacher": teacher,
                "category": cat_cloud,
                "short_description": "Learn containerization, automated CI/CD pipelines, and microservice orchestration.",
                "description": "Hands-on guide to containerizing web applications, writing production docker-compose topologies, and deploying to cloud clusters.",
                "price": Decimal("1999.00"),
                "discount_price": Decimal("999.00"),
                "currency": "INR",
                "status": CourseStatus.PUBLISHED,
                "difficulty": DifficultyLevel.ADVANCED,
                "is_featured": True,
                "estimated_duration": 360,
                "learning_objectives": [
                    "Containerize multi-container web stacks",
                    "Write robust production Dockerfiles and Nginx reverse proxies",
                ],
                "requirements": ["Linux command line basics"],
                "published_at": timezone.now(),
            },
        )

        c3, _ = Course.objects.get_or_create(
            slug="python-for-beginners-free-crash-course",
            defaults={
                "title": "Python for Beginners: 2026 Crash Course",
                "teacher": teacher,
                "category": cat_web,
                "short_description": "Start your programming journey with Python from scratch.",
                "description": "Learn variables, data structures, loops, functions, and object-oriented programming with interactive coding challenges.",
                "price": Decimal("0.00"),
                "is_free": True,
                "currency": "INR",
                "status": CourseStatus.PUBLISHED,
                "difficulty": DifficultyLevel.BEGINNER,
                "is_featured": False,
                "estimated_duration": 120,
                "learning_objectives": ["Write clean Python code", "Understand core algorithms and data structures"],
                "requirements": ["No prior experience required"],
                "published_at": timezone.now(),
            },
        )
        self.stdout.write(self.style.SUCCESS("[OK] Created 3 Courses (2 Paid, 1 Free)"))

        # 4. Sections & Lectures for Course 1
        s1, _ = Section.objects.get_or_create(course=c1, title="Module 1: Foundations & Architecture", defaults={"order": 1})
        s2, _ = Section.objects.get_or_create(course=c1, title="Module 2: Database Modeling & Advanced ORM", defaults={"order": 2})

        l1, _ = Lecture.objects.get_or_create(
            section=s1,
            title="1.1 Platform Architecture Overview",
            defaults={
                "order": 1,
                "is_free_preview": True,
                "is_published": True,
                "estimated_duration": 600,
                "description": "High-level overview of our LMS multi-tier architecture, role isolation, and security design.",
            },
        )
        LectureVideo.objects.get_or_create(
            lecture=l1,
            defaults={
                "storage_key": "videos/demo-intro.mp4",
                "original_filename": "demo-intro.mp4",
                "duration_seconds": 600,
                "file_size_bytes": 104857600,
                "mime_type": "video/mp4",
            },
        )
        LectureNote.objects.get_or_create(
            lecture=l1,
            title="Architecture Blueprint & Cheat Sheet",
            defaults={
                "note_type": NoteType.HTML,
                "html_content": "<p>Review the architecture diagram and system boundaries before proceeding to the code walk-through.</p>",
            },
        )

        l2, _ = Lecture.objects.get_or_create(
            section=s1,
            title="1.2 Setting Up the Containerized Environment",
            defaults={
                "order": 2,
                "is_free_preview": False,
                "is_published": True,
                "estimated_duration": 900,
                "description": "Step-by-step walkthrough of starting Docker Compose with PostgreSQL, Redis, and MinIO.",
            },
        )
        LectureVideo.objects.get_or_create(
            lecture=l2,
            defaults={
                "storage_key": "videos/docker-setup.mp4",
                "original_filename": "docker-setup.mp4",
                "duration_seconds": 900,
                "file_size_bytes": 157286400,
                "mime_type": "video/mp4",
            },
        )

        l3, _ = Lecture.objects.get_or_create(
            section=s2,
            title="2.1 Normalization and Foreign Keys",
            defaults={
                "order": 1,
                "is_free_preview": False,
                "is_published": True,
                "estimated_duration": 1200,
                "description": "Deep dive into model relationships, unique constraints, and database indexes.",
            },
        )
        LectureVideo.objects.get_or_create(
            lecture=l3,
            defaults={
                "storage_key": "videos/orm-deep-dive.mp4",
                "original_filename": "orm-deep-dive.mp4",
                "duration_seconds": 1200,
                "file_size_bytes": 209715200,
                "mime_type": "video/mp4",
            },
        )
        self.stdout.write(self.style.SUCCESS("[OK] Created Sections, Lectures, Videos, and Notes"))

        # 5. Coupons
        Coupon.objects.get_or_create(
            code="WELCOME50",
            defaults={
                "discount_type": DiscountType.PERCENTAGE,
                "discount_value": Decimal("50.00"),
                "valid_from": timezone.now() - timedelta(days=1),
                "valid_until": timezone.now() + timedelta(days=90),
                "is_active": True,
                "max_uses_per_user": 1,
            },
        )
        Coupon.objects.get_or_create(
            code="SAVE500",
            defaults={
                "discount_type": DiscountType.FIXED,
                "discount_value": Decimal("500.00"),
                "minimum_order_amount": Decimal("1000.00"),
                "valid_from": timezone.now() - timedelta(days=1),
                "valid_until": timezone.now() + timedelta(days=90),
                "is_active": True,
                "max_uses_per_user": 2,
            },
        )
        self.stdout.write(self.style.SUCCESS("[OK] Created 2 Coupons (WELCOME50, SAVE500)"))

        self.stdout.write(self.style.SUCCESS("\nEduFlow LMS demo data seeded successfully!"))
