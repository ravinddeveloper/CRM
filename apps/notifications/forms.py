"""Forms for Announcement creation and management."""
from django import forms
from apps.courses.models import Course
from .models import Announcement, AnnouncementPriority


class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ["title", "content", "course", "priority", "is_pinned", "is_published"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "w-full px-4 py-2.5 bg-gray-950 border border-gray-800 rounded-xl text-sm text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all",
                    "placeholder": "Enter a descriptive announcement headline...",
                }
            ),
            "content": forms.Textarea(
                attrs={
                    "rows": 6,
                    "class": "w-full px-4 py-2.5 bg-gray-950 border border-gray-800 rounded-xl text-sm text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all font-sans",
                    "placeholder": "Write full announcement details, guidelines, links, or instructions...",
                }
            ),
            "course": forms.Select(
                attrs={
                    "class": "w-full px-4 py-2.5 bg-gray-950 border border-gray-800 rounded-xl text-sm text-white focus:outline-none focus:border-indigo-500",
                }
            ),
            "priority": forms.Select(
                attrs={
                    "class": "w-full px-4 py-2.5 bg-gray-950 border border-gray-800 rounded-xl text-sm text-white focus:outline-none focus:border-indigo-500",
                }
            ),
            "is_pinned": forms.CheckboxInput(
                attrs={
                    "class": "w-4 h-4 rounded border-gray-700 bg-gray-950 text-indigo-600 focus:ring-indigo-500 focus:ring-offset-gray-900",
                }
            ),
            "is_published": forms.CheckboxInput(
                attrs={
                    "class": "w-4 h-4 rounded border-gray-700 bg-gray-950 text-indigo-600 focus:ring-indigo-500 focus:ring-offset-gray-900",
                }
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["course"].required = False
        self.fields["course"].empty_label = "🌐 Platform-Wide (Visible to All Students)"
        if user and not user.is_admin and getattr(user, "is_teacher", False):
            # Teacher can only target their own courses
            self.fields["course"].queryset = Course.objects.filter(teacher=user)
