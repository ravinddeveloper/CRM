from rest_framework import generics, permissions
from rest_framework.pagination import PageNumberPagination

from apps.enrollments.models import Enrollment
from apps.enrollments.serializers import EnrollmentSerializer


class StandardResultsPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class EnrollmentListAPIView(generics.ListAPIView):
    """
    List enrollments for current authenticated user.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = EnrollmentSerializer
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        return (
            Enrollment.objects.filter(user=self.request.user)
            .select_related("course", "course__teacher")
            .order_by("-created_at")
        )
