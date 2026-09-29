"""Local filesystem storage backend (for development without MinIO)."""
import logging
import os
import shutil
from typing import IO

from django.conf import settings

from .base import BaseStorageService

logger = logging.getLogger("apps.storage")


class LocalStorageService(BaseStorageService):
    """
    Development storage backend using local filesystem.
    NOT suitable for production use.
    Files stored under MEDIA_ROOT/private/.
    """

    def __init__(self):
        self._base_dir = os.path.join(str(settings.MEDIA_ROOT), "private")
        os.makedirs(self._base_dir, exist_ok=True)

    def _full_path(self, key: str) -> str:
        # Sanitize key to prevent path traversal
        safe_key = key.lstrip("/").replace("..", "")
        return os.path.join(self._base_dir, safe_key)

    def upload_file(self, key: str, file_obj: IO, content_type: str, metadata: dict | None = None) -> str:
        path = self._full_path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            shutil.copyfileobj(file_obj, f)
        logger.info("LocalStorage: stored %s", key)
        return key

    def generate_signed_url(
        self,
        key: str,
        expiry_seconds: int = 3600,
        response_content_type: str | None = None,
        download_filename: str | None = None,
    ) -> str:
        """For local dev, return a special Django serve URL with a token."""
        import hashlib
        import time

        from django.conf import settings

        # Create a simple time-based token (not cryptographically strong, dev only)
        secret = settings.SECRET_KEY
        expires = int(time.time()) + expiry_seconds
        data = f"{key}:{expires}:{secret}"
        token = hashlib.sha256(data.encode()).hexdigest()[:32]

        base_url = getattr(settings, "PLATFORM_URL", "http://localhost:8000")
        return f"{base_url}/private-media/?key={key}&token={token}&expires={expires}"

    def delete_file(self, key: str) -> None:
        path = self._full_path(key)
        if os.path.exists(path):
            os.remove(path)
            logger.info("LocalStorage: deleted %s", key)

    def file_exists(self, key: str) -> bool:
        return os.path.exists(self._full_path(key))

    def get_file_size(self, key: str) -> int:
        path = self._full_path(key)
        if os.path.exists(path):
            return os.path.getsize(path)
        return 0
