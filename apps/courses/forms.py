"""Course forms for teacher dashboard."""
from django import forms

from .models import Course, Section


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = [
            "title", "short_description", "description", "thumbnail",
            "category", "tags", "price", "discount_price", "currency",
            "is_free", "difficulty", "language", "estimated_duration",
            "learning_objectives", "requirements",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 8}),
            "short_description": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_price(self):
        price = self.cleaned_data["price"]
        if price < 0:
            raise forms.ValidationError("Price cannot be negative.")
        return price


class SectionForm(forms.ModelForm):
    class Meta:
        model = Section
        fields = ["title", "description", "is_published"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}
