from rest_framework import serializers

from apps.courses.serializers import CourseListSerializer
from apps.enrollments.models import Enrollment


class EnrollmentSerializer(serializers.ModelSerializer):
    course_detail = CourseListSerializer(source="course", read_only=True)
    user = serializers.CharField(source="user.id", read_only=True)

    class Meta:
        model = Enrollment
        fields = [
            "id",
            "user",
            "course",
            "course_detail",
            "status",
            "access_type",
            "expires_at",
            "created_at",
        ]
