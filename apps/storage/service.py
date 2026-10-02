"""Storage service factory - select backend from settings."""
import logging

from django.conf import settings

from .base import BaseStorageService

logger = logging.getLogger("apps.storage")

_service_cache = None


def get_storage_service() -> BaseStorageService:
    """Return the configured storage service instance (singleton)."""
    global _service_cache
    if _service_cache is not None:
        return _service_cache

    backend = getattr(settings, "STORAGE_BACKEND", "local").lower()
    logger.info("Initializing storage backend: %s", backend)

    if backend == "minio":
        from .minio import MinIOStorageService
        _service_cache = MinIOStorageService()
    elif backend == "s3":
        from .s3 import S3StorageService
        _service_cache = S3StorageService()
    elif backend == "azure":
        from .azure import AzureBlobStorageService
        _service_cache = AzureBlobStorageService()
    elif backend == "gdrive":
        from .gdrive import GoogleDriveStorageService
        _service_cache = GoogleDriveStorageService()
    elif backend == "local":
        from .local import LocalStorageService
        _service_cache = LocalStorageService()
    else:
        raise ValueError(f"Unknown STORAGE_BACKEND: '{backend}'. Choices: local, minio, s3, azure, gdrive")

    return _service_cache


def reset_storage_service():
    """Reset the cached service (useful in tests)."""
    global _service_cache
    _service_cache = None


class StorageService:
    """Convenience facade for storage service operations."""

    @classmethod
    def get_presigned_url(cls, storage_key: str, expires_in: int = 3600) -> str:
        svc = get_storage_service()
        if hasattr(svc, "generate_signed_url"):
            return svc.generate_signed_url(storage_key, expires_in)
        if hasattr(svc, "get_presigned_url"):
            return svc.get_presigned_url(storage_key, expires_in)
        return f"/media/{storage_key}?expires={expires_in}"

    @classmethod
    def generate_signed_url(
        cls,
        key: str,
        expiry_seconds: int = 3600,
        response_content_type: str | None = None,
        download_filename: str | None = None,
    ) -> str:
        svc = get_storage_service()
        if hasattr(svc, "generate_signed_url"):
            return svc.generate_signed_url(
                key=key,
                expiry_seconds=expiry_seconds,
                response_content_type=response_content_type,
                download_filename=download_filename,
            )
        return cls.get_presigned_url(key, expires_in=expiry_seconds)

    @classmethod
    def upload_file(
        cls,
        key: str,
        file_obj,
        content_type: str = "application/octet-stream",
        metadata: dict | None = None,
    ) -> str:
        svc = get_storage_service()
        return svc.upload_file(key, file_obj, content_type, metadata=metadata)

    @classmethod
    def delete_file(cls, key: str) -> None:
        svc = get_storage_service()
        svc.delete_file(key)

    @classmethod
    def file_exists(cls, key: str) -> bool:
        svc = get_storage_service()
        return svc.file_exists(key)

    @classmethod
    def get_file_size(cls, key: str) -> int:
        svc = get_storage_service()
        return svc.get_file_size(key)

    @classmethod
    def build_key(cls, prefix: str, filename: str) -> str:
        svc = get_storage_service()
        return svc.build_key(prefix, filename)


# File validation utilities
def validate_video_file(file_obj) -> tuple[bool, str]:
    """Validate an uploaded video file."""
    import os

    allowed_types = getattr(settings, "ALLOWED_VIDEO_TYPES", [
        "video/mp4", "video/webm", "video/ogg", "video/quicktime"
    ])
    allowed_extensions = {".mp4", ".webm", ".ogg", ".mov", ".mkv", ".m4v"}
    max_size_mb = getattr(settings, "MAX_VIDEO_SIZE_MB", 2048)

    content_type = getattr(file_obj, "content_type", "")
    _, ext = os.path.splitext(getattr(file_obj, "name", "").lower())

    if content_type not in allowed_types and ext not in allowed_extensions:
        return False, f"Video type '{content_type or ext}' is not allowed. Allowed: {', '.join(allowed_types)}"

    size_mb = getattr(file_obj, "size", 0) / (1024 * 1024)
    if size_mb > max_size_mb:
        return False, f"File is too large ({size_mb:.1f}MB). Maximum: {max_size_mb}MB"

    return True, ""


def validate_document_file(file_obj) -> tuple[bool, str]:
    """Validate an uploaded document, study material, or notes file."""
    import os
    allowed_types = getattr(settings, "ALLOWED_DOCUMENT_TYPES", [
        "application/pdf",
        "text/plain",
        "text/markdown",
        "text/csv",
        "text/html",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
        "application/x-zip-compressed",
        "application/octet-stream",
        "image/png",
        "image/jpeg",
        "image/webp",
    ])
    allowed_extensions = {
        ".pdf", ".txt", ".md", ".doc", ".docx", ".ppt", ".pptx",
        ".xls", ".xlsx", ".zip", ".tar", ".gz", ".png", ".jpg", ".jpeg",
        ".webp", ".ipynb", ".py", ".csv", ".json"
    }
    max_size_mb = getattr(settings, "MAX_DOCUMENT_SIZE_MB", 100)

    content_type = getattr(file_obj, "content_type", "")
    _, ext = os.path.splitext(getattr(file_obj, "name", "").lower())

    if content_type not in allowed_types and ext not in allowed_extensions:
        return False, f"File format '{ext or content_type}' is not supported. Allowed formats: PDF, Word, PowerPoint, Text, Markdown, ZIP archives, and Images."

    size_mb = getattr(file_obj, "size", 0) / (1024 * 1024)
    if size_mb > max_size_mb:
        return False, f"File is too large ({size_mb:.1f}MB). Maximum: {max_size_mb}MB"

    return True, ""


def safe_filename(filename: str) -> str:
    """Sanitize an uploaded filename."""
    import os
    import re
    # Strip directory components to avoid path traversal
    clean_name = os.path.basename(filename)
    # Get extension
    name, ext = os.path.splitext(clean_name)
    # Remove unsafe characters
    name = re.sub(r"[^\w\-_.]", "_", name)[:100]
    ext = re.sub(r"[^\w.]", "", ext)[:10]
    return f"{name}{ext}" if ext else name
