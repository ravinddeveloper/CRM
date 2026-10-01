"""Notification API endpoints independent of Django notification models."""
from math import ceil

from rest_framework import permissions, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.notifications.serializers import NotificationSerializer
from apps.notifications.services import NotificationService
from infrastructure.database.exceptions import EntityNotFoundError


class NotificationListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            page = max(1, int(request.query_params.get("page", "1")))
            page_size = min(100, max(1, int(request.query_params.get("page_size", "20"))))
        except (TypeError, ValueError):
            return Response(
                {"success": False, "error": {"message": "Page and page_size must be whole numbers."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        count, notifications = NotificationService.list_for_user(
            str(request.user.id), limit=page_size, offset=(page - 1) * page_size
        )
        total_pages = max(1, ceil(count / page_size))
        if page > total_pages:
            raise NotFound("Invalid page.")

        def page_url(number):
            query = request.query_params.copy()
            query["page"] = str(number)
            query["page_size"] = str(page_size)
            return request.build_absolute_uri(f"{request.path}?{query.urlencode()}")

        return Response({
            "success": True,
            "count": count,
            "next": page_url(page + 1) if page < total_pages else None,
            "previous": page_url(page - 1) if page > 1 else None,
            "total_pages": total_pages,
            "current_page": page,
            "results": NotificationSerializer(notifications, many=True).data,
        })


class MarkNotificationReadAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            NotificationService.mark_read(str(pk), str(request.user.id))
        except EntityNotFoundError as exc:
            raise NotFound("Notification was not found.") from exc
        return Response({"status": "success", "is_read": True}, status=status.HTTP_200_OK)
