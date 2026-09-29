"""Accounts forms."""
from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import ValidationError

User = get_user_model()


class LoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"placeholder": "Enter your email", "autofocus": True})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"placeholder": "Enter your password"})
    )
    remember_me = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._user = None

    def clean(self):
        email = self.cleaned_data.get("email", "").lower()
        password = self.cleaned_data.get("password", "")

        if email and password:
            user = authenticate(username=email, password=password)
            if user is None:
                raise ValidationError("Invalid email or password.")
            if not user.is_active:
                raise ValidationError("Your account is inactive. Please contact support.")
            self._user = user
        return self.cleaned_data

    def get_user(self):
        return self._user


class RegisterForm(forms.Form):
    first_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"placeholder": "First name"}))
    last_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"placeholder": "Last name"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"placeholder": "Email address"}))
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"placeholder": "Password (min 8 characters)"}),
        min_length=8,
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={"placeholder": "Confirm password"}),
    )
    agree_terms = forms.BooleanField(
        required=True,
        error_messages={"required": "You must accept the terms and conditions."},
    )

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Passwords do not match.")
        return cleaned


class ProfileUpdateForm(forms.Form):
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    bio = forms.CharField(max_length=1000, required=False, widget=forms.Textarea(attrs={"rows": 4}))
    phone = forms.CharField(max_length=20, required=False)
    website = forms.URLField(required=False)
    linkedin = forms.URLField(required=False)
    twitter = forms.URLField(required=False)
    country = forms.CharField(max_length=100, required=False)
    city = forms.CharField(max_length=100, required=False)
    avatar = forms.ImageField(required=False)

    def __init__(self, *args, instance=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = instance
        self.user = user
        if user:
            self.fields["first_name"].initial = user.first_name
            self.fields["last_name"].initial = user.last_name
        if instance:
            self.fields["bio"].initial = instance.bio
            self.fields["phone"].initial = instance.phone
            self.fields["website"].initial = instance.website
            self.fields["linkedin"].initial = instance.linkedin
            self.fields["twitter"].initial = instance.twitter
            self.fields["country"].initial = instance.country
            self.fields["city"].initial = instance.city


class PasswordChangeForm(forms.Form):
    old_password = forms.CharField(widget=forms.PasswordInput(attrs={"placeholder": "Current password"}))
    new_password1 = forms.CharField(
        label="New Password",
        widget=forms.PasswordInput(attrs={"placeholder": "New password"}),
        min_length=8,
    )
    new_password2 = forms.CharField(
        label="Confirm New Password",
        widget=forms.PasswordInput(attrs={"placeholder": "Confirm new password"}),
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("new_password1")
        p2 = cleaned.get("new_password2")
        if p1 and p2 and p1 != p2:
            self.add_error("new_password2", "Passwords do not match.")
        return cleaned


class ForgotPasswordForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"placeholder": "Your email address"}))


class ResetPasswordForm(forms.Form):
    password1 = forms.CharField(
        label="New Password",
        widget=forms.PasswordInput(attrs={"placeholder": "New password"}),
        min_length=8,
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={"placeholder": "Confirm new password"}),
    )

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Passwords do not match.")
        return cleaned


class TwoFactorVerifyForm(forms.Form):
    """Form to verify 6-digit TOTP code or emergency backup code."""
    code = forms.CharField(
        max_length=20,
        min_length=6,
        widget=forms.TextInput(attrs={
            "placeholder": "e.g. 123456 or 8-char backup code",
            "autocomplete": "one-time-code",
            "autofocus": True,
        }),
    )


class TwoFactorDisableForm(forms.Form):
    """Form to confirm password before disabling 2FA."""
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "placeholder": "Current account password",
        })
    )


class NotificationPreferencesForm(forms.Form):
    """Form for email and learning notification toggles."""
    notification_email = forms.BooleanField(required=False)
    notification_course_updates = forms.BooleanField(required=False)
    notification_new_lecture = forms.BooleanField(required=False)
