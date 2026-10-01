from django import forms

from apps.accounts.models import UserRole
from apps.courses.models import Course

from .models import Session


class SessionManagementForm(forms.ModelForm):
    starts_at = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
    )
    ends_at = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
    )

    class Meta:
        model = Session
        fields = (
            "title", "description", "session_type", "status", "starts_at", "ends_at", "instructor", "course",
            "location_name", "address", "meeting_url", "latitude", "longitude", "geofence_radius_meters",
            "capacity", "booking_required", "attendance_required", "membership_required", "allow_waitlist",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "address": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        User = Session._meta.get_field("instructor").remote_field.model
        self.fields["instructor"].queryset = User.objects.filter(
            role__in=[UserRole.TEACHER, UserRole.EMPLOYEE, UserRole.ADMIN], is_active=True
        ).order_by("first_name", "last_name", "email")
        self.fields["course"].queryset = Course.objects.order_by("title")
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "h-4 w-4 rounded border-gray-600 bg-gray-800 text-indigo-500"
            else:
                field.widget.attrs["class"] = "w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-100"
