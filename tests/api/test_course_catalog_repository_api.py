from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient


class CatalogRepositoryApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.records = [
            {
                "id": "518f1675-19ba-46c0-9737-14a66da84fc8", "title": "Catalog Course",
                "slug": "catalog-course", "short_description": "Short", "thumbnail": None,
                "category": {"id": "518f1675-19ba-46c0-9737-14a66da84fc9", "name": "Music",
                             "slug": "music", "description": "", "icon": ""},
                "teacher_name": "Teacher", "price": Decimal("100.00"),
                "discount_price": None, "effective_price": Decimal("100.00"), "currency": "INR",
                "is_free": False, "status": "published", "is_featured": False,
                "difficulty": "beginner", "estimated_duration": 60,
                "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            }
        ] * 11
        self.repository = type("Repository", (), {
            "list_published": self.list_published,
            "list_categories": self.list_categories,
            "get_category_by_slug": self.get_category_by_slug,
        })()
        self.calls = []

    def list_categories(self, *, root_only=False):
        return [{
            "id": "518f1675-19ba-46c0-9737-14a66da84fc9", "name": "Music",
            "slug": "music", "description": "Lessons", "icon": "🎵",
        }]

    def get_category_by_slug(self, slug):
        return self.list_categories()[0] if slug == "music" else None

    def list_published(self, **kwargs):
        self.calls.append(kwargs)
        start = kwargs["offset"]
        end = start + kwargs["limit"]
        return 11, self.records[start:end]

    def test_api_uses_repository_filters_and_keeps_page_response_contract(self):
        with patch("apps.courses.api_views.get_course_catalog_repository", return_value=self.repository):
            response = self.client.get("/api/v1/courses/?search=music&page=2&page_size=5")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 11)
        self.assertEqual(len(response.data["results"]), 5)
        self.assertIn("page=3", response.data["next"])
        self.assertEqual(self.calls[0]["search"], "music")
        self.assertEqual(self.calls[0]["limit"], 5)
        self.assertEqual(self.calls[0]["offset"], 5)
        self.assertEqual(response.data["results"][0]["category"]["slug"], "music")

    def test_api_filter_values_match_existing_true_false_behavior(self):
        with patch("apps.courses.api_views.get_course_catalog_repository", return_value=self.repository):
            self.client.get("/api/v1/courses/?is_free=false")
            self.client.get("/api/v1/courses/?is_free=1")

        self.assertIs(self.calls[0]["is_free"], False)
        self.assertIs(self.calls[1]["is_free"], True)

    def test_last_page_fetches_the_last_page_of_records(self):
        with patch("apps.courses.api_views.get_course_catalog_repository", return_value=self.repository):
            response = self.client.get("/api/v1/courses/?page=last&page_size=5")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.calls[-1]["offset"], 10)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertIsNone(response.data["next"])

    def test_category_api_reads_from_selected_catalog_repository(self):
        with patch("apps.courses.api_views.get_course_catalog_repository", return_value=self.repository):
            response = self.client.get("/api/v1/courses/categories/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["slug"], "music")
