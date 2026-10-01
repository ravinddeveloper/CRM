from django.core.files.storage import default_storage
from rest_framework import serializers

from apps.courses.models import Category, Course, Section, Tag
from apps.lectures.models import Lecture


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "description", "icon"]


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name", "slug"]


class LecturePreviewSerializer(serializers.ModelSerializer):
    duration_seconds = serializers.IntegerField(source="estimated_duration", read_only=True)

    class Meta:
        model = Lecture
        fields = ["id", "title", "order", "estimated_duration", "duration_seconds", "is_free_preview"]


class SectionSerializer(serializers.ModelSerializer):
    lectures = LecturePreviewSerializer(many=True, read_only=True)

    class Meta:
        model = Section
        fields = ["id", "title", "order", "lectures"]


class CourseListSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    teacher_name = serializers.CharField(source="teacher.full_name", read_only=True)
    effective_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Course
        fields = [
            "id",
            "title",
            "slug",
            "short_description",
            "thumbnail",
            "category",
            "teacher_name",
            "price",
            "discount_price",
            "effective_price",
            "currency",
            "is_free",
            "status",
            "is_featured",
            "difficulty",
            "estimated_duration",
            "created_at",
        ]


class CourseCatalogRecordSerializer(serializers.Serializer):
    """Stable API representation for SQL rows and Mongo catalog documents."""
    id = serializers.UUIDField()
    title = serializers.CharField()
    slug = serializers.CharField()
    short_description = serializers.CharField()
    thumbnail = serializers.SerializerMethodField()
    category = CategorySerializer(read_only=True, allow_null=True)
    teacher_name = serializers.CharField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    discount_price = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    effective_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField()
    is_free = serializers.BooleanField()
    status = serializers.CharField()
    is_featured = serializers.BooleanField()
    difficulty = serializers.CharField()
    estimated_duration = serializers.IntegerField()
    created_at = serializers.DateTimeField()

    def get_thumbnail(self, record):
        path = record.get("thumbnail")
        if not path:
            return None
        url = default_storage.url(path)
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request and not url.startswith(("http://", "https://")) else url


class CourseDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    sections = SectionSerializer(many=True, read_only=True)
    teacher_name = serializers.CharField(source="teacher.full_name", read_only=True)
    teacher_bio = serializers.CharField(source="teacher.profile.bio", default="", read_only=True)
    effective_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Course
        fields = [
            "id",
            "title",
            "slug",
            "short_description",
            "description",
            "thumbnail",
            "preview_video_key",
            "category",
            "tags",
            "teacher_name",
            "teacher_bio",
            "price",
            "discount_price",
            "effective_price",
            "currency",
            "is_free",
            "status",
            "is_featured",
            "difficulty",
            "language",
            "estimated_duration",
            "learning_objectives",
            "requirements",
            "sections",
            "created_at",
            "updated_at",
        ]
