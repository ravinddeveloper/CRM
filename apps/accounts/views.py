"""Accounts views - login, register, logout, profile."""
import logging

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from apps.notifications.tasks import send_password_reset_email, send_verification_email

from .forms import (
    ForgotPasswordForm,
    LoginForm,
    PasswordChangeForm,
    ProfileUpdateForm,
    RegisterForm,
    ResetPasswordForm,
)
from .services import AccountService

logger = logging.getLogger("apps.accounts")


@never_cache
@require_http_methods(["GET", "POST"])
def login_view(request):
    """User login view with rate limiting."""
    if request.user.is_authenticated:
        return redirect("dashboard:redirect")

    form = LoginForm(data=request.POST or None)

    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        if user.is_suspended:
            messages.error(request, "Your account has been suspended. Contact support.")
            return render(request, "accounts/login.html", {"form": form})

        login(request, user)
        logger.info("User logged in: %s from %s", user.email, request.META.get("REMOTE_ADDR"))
        next_url = request.GET.get("next", "")
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        return redirect("dashboard:redirect")

    return render(request, "accounts/login.html", {"form": form})


@require_http_methods(["POST"])
def logout_view(request):
    """User logout - POST only for CSRF protection."""
    if request.user.is_authenticated:
        logger.info("User logged out: %s", request.user.email)
        logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect("marketplace:course_list")


@never_cache
@require_http_methods(["GET", "POST"])
def register_view(request):
    """Student registration view."""
    if request.user.is_authenticated:
        return redirect("dashboard:redirect")

    form = RegisterForm(data=request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            user = AccountService.register_user(
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password1"],
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
            )
            # Send verification email asynchronously
            send_verification_email.delay(user.id)
            messages.success(
                request,
                "Account created! Please check your email to verify your account."
            )
            return redirect("accounts:verification_sent")
        except ValidationError as e:
            form.add_error(None, str(e))

    return render(request, "accounts/register.html", {"form": form})


def verification_sent_view(request):
    """Confirmation page after registration."""
    return render(request, "accounts/verification_sent.html")


def verify_email_view(request, token):
    """Verify email using token from link."""
    try:
        AccountService.verify_email(str(token))
        messages.success(request, "Email verified successfully! You can now log in.")
        return redirect("accounts:login")
    except ValidationError as e:
        messages.error(request, str(e))
        return render(request, "accounts/verification_invalid.html")


@require_http_methods(["GET", "POST"])
def forgot_password_view(request):
    """Initiate password reset flow."""
    form = ForgotPasswordForm(data=request.POST or None)

    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        ip = request.META.get("REMOTE_ADDR")
        token = AccountService.create_password_reset_token(email, ip_address=ip)
        if token:
            send_password_reset_email.delay(token.id)
        # Always show success to prevent email enumeration
        messages.success(
            request,
            "If an account exists with this email, you will receive a password reset link."
        )
        return redirect("accounts:forgot_password")

    return render(request, "accounts/forgot_password.html", {"form": form})


@require_http_methods(["GET", "POST"])
def reset_password_view(request, token):
    """Reset password using token."""
    form = ResetPasswordForm(data=request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            AccountService.reset_password(
                token_str=str(token),
                new_password=form.cleaned_data["password1"],
            )
            messages.success(request, "Password reset successful. You can now log in.")
            return redirect("accounts:login")
        except ValidationError as e:
            messages.error(request, str(e))

    return render(request, "accounts/reset_password.html", {"form": form, "token": token})


@login_required
@require_http_methods(["GET", "POST"])
def profile_view(request):
    """View and update user profile."""
    user = request.user
    form = ProfileUpdateForm(
        data=request.POST or None,
        files=request.FILES or None,
        instance=user.profile,
        user=user,
    )

    if request.method == "POST" and form.is_valid():
        try:
            AccountService.update_profile(
                user=user,
                **form.cleaned_data,
            )
            messages.success(request, "Profile updated successfully.")
            if request.htmx:
                return render(request, "accounts/_profile_form.html", {"form": form, "saved": True})
            return redirect("accounts:profile")
        except Exception as e:
            messages.error(request, str(e))

    return render(request, "accounts/profile.html", {"form": form, "profile_user": user})


@login_required
@require_http_methods(["GET", "POST"])
def change_password_view(request):
    """Change password for logged-in users."""
    form = PasswordChangeForm(user=request.user, data=request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            AccountService.change_password(
                user=request.user,
                old_password=form.cleaned_data["old_password"],
                new_password=form.cleaned_data["new_password1"],
            )
            messages.success(request, "Password changed successfully. Please log in again.")
            logout(request)
            return redirect("accounts:login")
        except ValidationError as e:
            form.add_error("old_password", str(e))

    return render(request, "accounts/change_password.html", {"form": form})
