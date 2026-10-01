"""Backend-neutral notification API serialization."""
from rest_framework import serializers


class NotificationSerializer(serializers.Serializer):
    id = serializers.CharField()
    title = serializers.CharField()
    message = serializers.CharField()
    notification_type = serializers.CharField()
    is_read = serializers.BooleanField()
    action_url = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()
