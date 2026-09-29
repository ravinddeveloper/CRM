"""Lecture forms."""
from django import forms

from .models import Lecture


class LectureForm(forms.ModelForm):
    class Meta:
        model = Lecture
        fields = ["title", "description", "order", "is_free_preview", "is_published", "estimated_duration"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}
