from rest_framework import serializers

from apps.courses.serializers import CourseListSerializer


class EnrollmentSerializer(serializers.Serializer):
    id = serializers.CharField()
    user = serializers.CharField(source="record.user_id")
    course = serializers.CharField(source="record.course_id")
    course_detail = CourseListSerializer(source="course_object", read_only=True, allow_null=True)
    status = serializers.CharField(source="record.status")
    access_type = serializers.CharField(source="record.access_type")
    expires_at = serializers.DateTimeField(source="record.expires_at", allow_null=True)
    created_at = serializers.DateTimeField(source="record.created_at")

    def to_representation(self, instance):
        record, course_object = instance
        return super().to_representation({
            "id": record.id, "record": record, "course_object": course_object,
        })
