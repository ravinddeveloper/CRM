"""Google Drive storage backend.

Authentication options (in priority order):
1. ``GDRIVE_SERVICE_ACCOUNT_JSON`` – path to a service-account key JSON file.
2. ``GDRIVE_SERVICE_ACCOUNT_INFO`` – raw JSON string of the service-account key
   (suitable for Docker secrets / env-var injection without mounting a file).
3. Application Default Credentials (ADC) via ``google.auth.default()``.

Required Django settings / environment variables:
    GDRIVE_SERVICE_ACCOUNT_JSON   path to service-account key file (optional)
    GDRIVE_SERVICE_ACCOUNT_INFO   JSON string of service-account key (optional)
    GDRIVE_ROOT_FOLDER_ID         ID of the Drive folder used as root (required)
    GDRIVE_SHARED_DRIVE_ID        Shared-drive (Team Drive) ID (optional)
    GDRIVE_SIGNED_URL_EXPIRY      seconds for signed URL validity (default 3600)

Install the required Google libraries:
    pip install google-api-python-client google-auth
"""

from __future__ import annotations

import io
import json
import logging
import os
import tempfile
import time
from typing import IO

from django.conf import settings

from .base import BaseStorageService

logger = logging.getLogger("apps.storage")

_SCOPES = [
    "https://www.googleapis.com/auth/drive",
]

# MIME type used when uploading; Drive will accept any binary stream here.
_GDRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"


class GoogleDriveStorageService(BaseStorageService):
    """Storage backend that stores files in a Google Drive folder tree.

    Keys are treated as Unix-style relative paths (e.g. ``courses/123/video.mp4``).
    Each path component maps to a nested Drive folder; the final component is
    the file name.  The service caches folder-ID lookups for the process lifetime
    to minimise Drive API calls.

    Signed URLs are generated as time-limited, token-protected redirect URLs
    served through Django's ``/gdrive-media/`` view.  Drive's native sharing
    URLs are not used because they require the file to be publicly accessible.
    Use the ``GDRIVE_SIGNED_URL_EXPIRY`` setting (default 3 600 s) to control
    link lifetime.
    """

    # ------------------------------------------------------------------
    # Construction and authentication
    # ------------------------------------------------------------------

    def __init__(self) -> None:
        self._credentials = self._build_credentials()
        self._drive = self._build_service()
        self._root_folder_id: str = getattr(settings, "GDRIVE_ROOT_FOLDER_ID", "")
        self._shared_drive_id: str = getattr(settings, "GDRIVE_SHARED_DRIVE_ID", "")
        if not self._root_folder_id:
            raise ValueError(
                "GDRIVE_ROOT_FOLDER_ID must be set when STORAGE_BACKEND=gdrive. "
                "Create a folder in Google Drive, copy its ID from the URL, and "
                "set GDRIVE_ROOT_FOLDER_ID in your environment."
            )
        # Cache: relative-path prefix → Drive folder ID
        self._folder_cache: dict[str, str] = {}
        logger.info(
            "GoogleDriveStorageService ready (root=%s, shared_drive=%s)",
            self._root_folder_id,
            self._shared_drive_id or "none",
        )

    def _build_credentials(self):
        """Return google.oauth2 credentials using the configured auth method."""
        try:
            from google.oauth2 import service_account
            import google.auth
        except ImportError as exc:
            raise ImportError(
                "google-api-python-client and google-auth are required for the "
                "Google Drive storage backend. "
                "Install them with: pip install google-api-python-client google-auth"
            ) from exc

        # 1. Service-account JSON file path
        sa_file = getattr(settings, "GDRIVE_SERVICE_ACCOUNT_JSON", "") or os.environ.get(
            "GDRIVE_SERVICE_ACCOUNT_JSON", ""
        )
        if sa_file and os.path.isfile(sa_file):
            logger.debug("GDrive auth: service-account file %s", sa_file)
            return service_account.Credentials.from_service_account_file(sa_file, scopes=_SCOPES)

        # 2. Service-account JSON string
        sa_info_raw = getattr(settings, "GDRIVE_SERVICE_ACCOUNT_INFO", "") or os.environ.get(
            "GDRIVE_SERVICE_ACCOUNT_INFO", ""
        )
        if sa_info_raw:
            try:
                sa_info = json.loads(sa_info_raw)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "GDRIVE_SERVICE_ACCOUNT_INFO contains invalid JSON."
                ) from exc
            logger.debug("GDrive auth: service-account info from env string")
            return service_account.Credentials.from_service_account_info(sa_info, scopes=_SCOPES)

        # 3. Application Default Credentials
        logger.debug("GDrive auth: Application Default Credentials (ADC)")
        credentials, _ = google.auth.default(scopes=_SCOPES)
        return credentials

    def _build_service(self):
        """Build the Drive v3 resource client."""
        try:
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise ImportError(
                "google-api-python-client is required for Google Drive storage."
            ) from exc
        return build("drive", "v3", credentials=self._credentials, cache_discovery=False)

    # ------------------------------------------------------------------
    # Internal folder helpers
    # ------------------------------------------------------------------

    def _shared_drive_kwargs(self, *, list_op: bool = False) -> dict:
        """Return keyword args that opt into Shared Drive access when configured."""
        if not self._shared_drive_id:
            return {}
        if list_op:
            return {
                "corpora": "drive",
                "driveId": self._shared_drive_id,
                "includeItemsFromAllDrives": True,
                "supportsAllDrives": True,
            }
        return {
            "supportsAllDrives": True,
        }

    def _ensure_folder(self, path_prefix: str) -> str:
        """Return the Drive folder ID for *path_prefix*, creating it if needed.

        ``path_prefix`` is a slash-separated relative path
        (e.g. ``"courses/123/videos"``). Returns the ID of the deepest folder.
        """
        if path_prefix in self._folder_cache:
            return self._folder_cache[path_prefix]

        parts = [p for p in path_prefix.split("/") if p]
        parent_id = self._root_folder_id

        accumulated = ""
        for part in parts:
            accumulated = f"{accumulated}/{part}".lstrip("/")
            if accumulated in self._folder_cache:
                parent_id = self._folder_cache[accumulated]
                continue

            # Search for existing folder
            query = (
                f"name = {json.dumps(part)} "
                f"and '{parent_id}' in parents "
                f"and mimeType = '{_GDRIVE_FOLDER_MIME}' "
                f"and trashed = false"
            )
            results = (
                self._drive.files()
                .list(
                    q=query,
                    fields="files(id)",
                    pageSize=1,
                    **self._shared_drive_kwargs(list_op=True),
                )
                .execute()
            )
            existing = results.get("files", [])
            if existing:
                folder_id = existing[0]["id"]
            else:
                # Create the folder
                metadata = {
                    "name": part,
                    "mimeType": _GDRIVE_FOLDER_MIME,
                    "parents": [parent_id],
                }
                folder = (
                    self._drive.files()
                    .create(
                        body=metadata,
                        fields="id",
                        **self._shared_drive_kwargs(),
                    )
                    .execute()
                )
                folder_id = folder["id"]
                logger.debug("GDrive: created folder '%s' (id=%s)", part, folder_id)

            self._folder_cache[accumulated] = folder_id
            parent_id = folder_id

        return parent_id

    def _find_file_id(self, key: str) -> str | None:
        """Return the Drive file ID for *key*, or ``None`` if not found."""
        safe_key = key.lstrip("/")
        parts = safe_key.rsplit("/", 1)
        if len(parts) == 2:
            prefix, filename = parts
        else:
            prefix, filename = "", parts[0]

        parent_id = self._root_folder_id if not prefix else self._folder_cache.get(
            prefix
        )
        if parent_id is None:
            return None  # folder not yet created → file cannot exist

        query = (
            f"name = {json.dumps(filename)} "
            f"and '{parent_id}' in parents "
            f"and mimeType != '{_GDRIVE_FOLDER_MIME}' "
            f"and trashed = false"
        )
        results = (
            self._drive.files()
            .list(
                q=query,
                fields="files(id)",
                pageSize=1,
                **self._shared_drive_kwargs(list_op=True),
            )
            .execute()
        )
        files = results.get("files", [])
        return files[0]["id"] if files else None

    # ------------------------------------------------------------------
    # BaseStorageService interface
    # ------------------------------------------------------------------

    def upload_file(
        self,
        key: str,
        file_obj: IO,
        content_type: str,
        metadata: dict | None = None,
    ) -> str:
        """Upload *file_obj* to Drive at the path described by *key*.

        Returns *key* (the logical storage path). Overwrites an existing file
        at the same path by updating its content rather than creating a duplicate.
        """
        try:
            from googleapiclient.http import MediaIoBaseUpload
        except ImportError as exc:
            raise ImportError("google-api-python-client is required.") from exc

        safe_key = key.lstrip("/")
        parts = safe_key.rsplit("/", 1)
        prefix = parts[0] if len(parts) == 2 else ""
        filename = parts[-1]

        # Ensure the folder hierarchy exists
        parent_id = self._ensure_folder(prefix) if prefix else self._root_folder_id

        if hasattr(file_obj, "seek"):
            file_obj.seek(0)

        media = MediaIoBaseUpload(file_obj, mimetype=content_type, resumable=True)
        file_metadata: dict = {"name": filename, "parents": [parent_id]}

        # Check for existing file to update instead of duplicate
        existing_id = self._find_file_id(safe_key)
        try:
            if existing_id:
                # Update content only (no parents change needed)
                self._drive.files().update(
                    fileId=existing_id,
                    media_body=media,
                    fields="id",
                    **self._shared_drive_kwargs(),
                ).execute()
                logger.info("GDrive: updated file %s (id=%s)", safe_key, existing_id)
            else:
                result = (
                    self._drive.files()
                    .create(
                        body=file_metadata,
                        media_body=media,
                        fields="id",
                        **self._shared_drive_kwargs(),
                    )
                    .execute()
                )
                logger.info(
                    "GDrive: uploaded file %s (id=%s)", safe_key, result["id"]
                )
        except Exception as exc:
            logger.error("GDrive: failed to upload %s: %s", safe_key, exc)
            raise

        return safe_key

    def generate_signed_url(
        self,
        key: str,
        expiry_seconds: int = 3600,
        response_content_type: str | None = None,
        download_filename: str | None = None,
    ) -> str:
        """Generate a time-limited signed URL served via Django's gdrive-media view.

        Google Drive itself does not provide signed download URLs without making
        files public.  Instead we issue a HMAC-protected redirect URL that the
        Django view ``/gdrive-media/`` validates before streaming the file from
        Drive to the browser using a service-account token.
        """
        import hashlib
        import hmac
        import urllib.parse

        safe_key = key.lstrip("/")
        platform_url = getattr(settings, "PLATFORM_URL", "http://localhost:8000").rstrip("/")
        expires = int(time.time()) + expiry_seconds
        secret = str(settings.SECRET_KEY).encode()
        msg = f"{safe_key}:{expires}".encode()
        token = hmac.new(secret, msg, hashlib.sha256).hexdigest()

        params = {"key": safe_key, "token": token, "expires": expires}
        if download_filename:
            params["download"] = download_filename
        if response_content_type:
            params["content_type"] = response_content_type

        url = f"{platform_url}/gdrive-media/?{urllib.parse.urlencode(params)}"
        logger.debug("GDrive: generated signed URL for %s (expires in %ds)", safe_key, expiry_seconds)
        return url

    def delete_file(self, key: str) -> None:
        """Trash the file in Drive (Drive's soft-delete; permanently removes after 30 days)."""
        safe_key = key.lstrip("/")
        file_id = self._find_file_id(safe_key)
        if not file_id:
            logger.warning("GDrive: delete called for non-existent key %s", safe_key)
            return
        try:
            self._drive.files().delete(
                fileId=file_id,
                **self._shared_drive_kwargs(),
            ).execute()
            logger.info("GDrive: deleted file %s (id=%s)", safe_key, file_id)
        except Exception as exc:
            logger.error("GDrive: failed to delete %s: %s", safe_key, exc)
            raise

    def file_exists(self, key: str) -> bool:
        """Return ``True`` if a file with the given key exists in Drive."""
        return self._find_file_id(key.lstrip("/")) is not None

    def get_file_size(self, key: str) -> int:
        """Return the file size in bytes, or 0 if not found."""
        safe_key = key.lstrip("/")
        file_id = self._find_file_id(safe_key)
        if not file_id:
            return 0
        try:
            meta = (
                self._drive.files()
                .get(
                    fileId=file_id,
                    fields="size",
                    **self._shared_drive_kwargs(),
                )
                .execute()
            )
            return int(meta.get("size", 0))
        except Exception:
            return 0

    def stream_to_response(self, key: str) -> bytes:
        """Download the raw bytes of a Drive file.

        Used by the ``/gdrive-media/`` view to proxy content to the browser.
        """
        safe_key = key.lstrip("/")
        file_id = self._find_file_id(safe_key)
        if not file_id:
            raise FileNotFoundError(f"GDrive: file not found: {safe_key}")
        try:
            request = self._drive.files().get_media(
                fileId=file_id,
                **self._shared_drive_kwargs(),
            )
            buf = io.BytesIO()
            from googleapiclient.http import MediaIoBaseDownload

            downloader = MediaIoBaseDownload(buf, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            return buf.getvalue()
        except Exception as exc:
            logger.error("GDrive: failed to stream %s: %s", safe_key, exc)
            raise
