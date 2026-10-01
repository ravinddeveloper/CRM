from rest_framework import generics, permissions
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import NotFound
from django.core.paginator import InvalidPage

from apps.enrollments.repository_service import list_enrollments_for_user
from apps.enrollments.serializers import EnrollmentSerializer


class StandardResultsPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def paginate_repository(self, request, view, list_callback):
        self.request = request
        self.page_size = self.get_page_size(request)
        if self.page_size is None:
            self.page_size = 20
        count, _ = list_callback(limit=1, offset=0)
        page_number = self.get_page_number(request, self.django_paginator_class(range(count), self.page_size))
        if page_number in self.last_page_strings:
            page_number = self.django_paginator_class(range(count), self.page_size).num_pages or 1
        if not str(page_number).isdigit() or int(page_number) < 1:
            raise NotFound("Invalid page.")
        offset = (int(page_number) - 1) * self.page_size
        _, rows = list_callback(limit=self.page_size, offset=offset)
        paginator = self.django_paginator_class(range(count), self.page_size)
        try:
            self.page = paginator.page(page_number)
        except InvalidPage as exc:
            raise NotFound("Invalid page.") from exc
        self.page.object_list = rows
        return rows


class EnrollmentListAPIView(generics.GenericAPIView):
    """
    List enrollments for current authenticated user.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = EnrollmentSerializer
    pagination_class = StandardResultsPagination

    def get(self, request, *args, **kwargs):
        paginator = self.pagination_class()
        rows = paginator.paginate_repository(
            request, self,
            lambda **kwargs: list_enrollments_for_user(user_id=request.user.pk, **kwargs),
        )
        serializer = self.get_serializer(rows, many=True)
        return paginator.get_paginated_response(serializer.data)
