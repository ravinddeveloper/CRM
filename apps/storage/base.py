"""Base storage service interface."""
from abc import ABC, abstractmethod
from typing import IO


class BaseStorageService(ABC):
    """Abstract base class for all storage backends."""

    @abstractmethod
    def upload_file(
        self,
        key: str,
        file_obj: IO,
        content_type: str,
        metadata: dict | None = None,
    ) -> str:
        """Upload a file to storage. Returns the storage key."""
        ...

    @abstractmethod
    def generate_signed_url(
        self,
        key: str,
        expiry_seconds: int = 3600,
        response_content_type: str | None = None,
        download_filename: str | None = None,
    ) -> str:
        """Generate a temporary signed URL for private content."""
        ...

    @abstractmethod
    def delete_file(self, key: str) -> None:
        """Delete a file from storage."""
        ...

    @abstractmethod
    def file_exists(self, key: str) -> bool:
        """Check if a file exists in storage."""
        ...

    @abstractmethod
    def get_file_size(self, key: str) -> int:
        """Return file size in bytes."""
        ...

    def get_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Convenience alias for generate_signed_url."""
        return self.generate_signed_url(key, expiry_seconds=expires_in)

    def build_key(self, prefix: str, filename: str) -> str:
        """Build a storage key from prefix and filename."""
        import os
        import uuid
        ext = os.path.splitext(filename)[1].lower()
        unique_name = f"{uuid.uuid4().hex}{ext}"
        return f"{prefix.rstrip('/')}/{unique_name}"
