from django.urls import path

from apps.enrollments.api_views import EnrollmentListAPIView

app_name = "enrollments_api"

urlpatterns = [
    path("", EnrollmentListAPIView.as_view(), name="enrollment_list"),
]
