"""Private media server for local development + Google Drive proxy."""
import hashlib
import hmac
import mimetypes
import os
import time

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden


def private_media_view(request):
    """
    Serve signed private files during local development.
    Validates HMAC token and expiration timestamp before streaming the file.
    """
    key = request.GET.get("key", "").strip()
    token = request.GET.get("token", "").strip()
    expires = request.GET.get("expires", "").strip()

    if not key or not token or not expires:
        return HttpResponseForbidden("Missing authorization parameters.")

    try:
        expires_int = int(expires)
    except ValueError:
        return HttpResponseForbidden("Invalid expiration timestamp.")

    # Check if expired
    if time.time() > expires_int:
        return HttpResponseForbidden("Access link has expired. Please refresh the page to get a new signed link.")

    # Verify signature
    secret = settings.SECRET_KEY
    data = f"{key}:{expires}:{secret}"
    expected = hashlib.sha256(data.encode()).hexdigest()[:32]

    if not hmac.compare_digest(token, expected):
        return HttpResponseForbidden("Invalid signature token.")

    # Resolve safe path within MEDIA_ROOT/private
    safe_key = key.lstrip("/\\").replace("..", "")
    base_dir = os.path.abspath(os.path.join(str(settings.MEDIA_ROOT), "private"))
    full_path = os.path.abspath(os.path.join(base_dir, safe_key))

    # Path traversal protection (normalized for Windows path comparisons)
    if not os.path.normcase(full_path).startswith(os.path.normcase(base_dir)):
        return HttpResponseForbidden("Access denied.")

    if not os.path.exists(full_path) or not os.path.isfile(full_path):
        raise Http404("File not found.")

    # Detect MIME type
    content_type, _ = mimetypes.guess_type(full_path)
    if not content_type:
        content_type = "application/octet-stream"

    filename = os.path.basename(full_path)
    download_name = request.GET.get("download", "").strip()

    response = FileResponse(open(full_path, "rb"), content_type=content_type)
    if download_name:
        safe_dl = os.path.basename(download_name).replace('"', '')
        response["Content-Disposition"] = f'attachment; filename="{safe_dl}"'
    else:
        response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


def gdrive_media_view(request):
    """Proxy a Google Drive file to the browser after verifying the HMAC token.

    The URL is issued by ``GoogleDriveStorageService.generate_signed_url()``.
    Validation mirrors the same HMAC construction used on the signing side so
    that a tampered or expired URL is rejected without touching the Drive API.
    """
    key = request.GET.get("key", "").strip()
    token = request.GET.get("token", "").strip()
    expires = request.GET.get("expires", "").strip()

    if not key or not token or not expires:
        return HttpResponseForbidden("Missing authorization parameters.")

    try:
        expires_int = int(expires)
    except ValueError:
        return HttpResponseForbidden("Invalid expiration timestamp.")

    if time.time() > expires_int:
        return HttpResponseForbidden("Access link has expired. Please refresh the page to get a new signed link.")

    # Verify HMAC-SHA256 token
    secret = str(settings.SECRET_KEY).encode()
    msg = f"{key}:{expires}".encode()
    expected = hmac.new(secret, msg, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(token, expected):
        return HttpResponseForbidden("Invalid signature token.")

    # Determine content type
    download_filename = request.GET.get("download", "").strip()
    content_type = request.GET.get("content_type", "").strip()
    if not content_type:
        content_type, _ = mimetypes.guess_type(key)
        if not content_type:
            content_type = "application/octet-stream"

    # Stream from Google Drive
    try:
        from .gdrive import GoogleDriveStorageService
        backend = getattr(settings, "STORAGE_BACKEND", "local").lower()
        if backend != "gdrive":
            raise Http404("Google Drive storage is not the active backend.")

        from .service import get_storage_service
        svc = get_storage_service()
        if not isinstance(svc, GoogleDriveStorageService):
            raise Http404("Google Drive proxy requested but backend is not gdrive.")

        data = svc.stream_to_response(key)
    except FileNotFoundError:
        raise Http404("File not found in Google Drive.")
    except Exception as exc:
        import logging
        logging.getLogger("apps.storage").error("GDrive proxy error for %s: %s", key, exc)
        return HttpResponse("Failed to retrieve file.", status=502)

    response = HttpResponse(data, content_type=content_type)
    filename = os.path.basename(key)
    if download_filename:
        safe_dl = os.path.basename(download_filename).replace('"', '')
        response["Content-Disposition"] = f'attachment; filename="{safe_dl}"'
    else:
        response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response
