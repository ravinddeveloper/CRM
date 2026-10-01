"""Common views - error pages, dashboard redirect."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.core.exceptions import PermissionDenied


def error_400(request, exception=None):
    return render(request, "errors/400.html", status=400)


def error_403(request, exception=None):
    return render(request, "errors/403.html", status=403)


def error_404(request, exception=None):
    return render(request, "errors/404.html", status=404)


def error_500(request):
    return render(request, "errors/500.html", status=500)


@login_required
def dashboard_redirect(request):
    """Redirect users to their role-specific dashboard."""
    user = request.user
    if user.is_admin:
        return redirect("admin_panel:dashboard")
    elif user.is_teacher:
        return redirect("teacher:dashboard")
    elif user.is_employee:
        return redirect("scheduling:staff_attendance")
    elif user.role != "student":
        raise PermissionDenied("This account does not have a member dashboard.")
    else:
        return redirect("student:dashboard")
