"""Azure Blob Storage backend."""
import logging
from datetime import datetime, timedelta, timezone
from typing import IO

from django.conf import settings

from .base import BaseStorageService

logger = logging.getLogger("apps.storage")


class AzureBlobStorageService(BaseStorageService):
    """
    Storage backend for Azure Blob Storage.
    Requires `azure-storage-blob` package.
    """

    def __init__(self):
        try:
            from azure.storage.blob import BlobServiceClient
        except ImportError as exc:
            raise ImportError(
                "azure-storage-blob is required for Azure Blob Storage backend. "
                "Install it with: pip install azure-storage-blob"
            ) from exc

        self.account_name = getattr(settings, "AZURE_ACCOUNT_NAME", "")
        self.account_key = getattr(settings, "AZURE_ACCOUNT_KEY", "")
        self.container_name = getattr(settings, "AZURE_CONTAINER", "lms-content")
        self.connection_string = getattr(settings, "AZURE_CONNECTION_STRING", "")
        self.custom_domain = getattr(settings, "AZURE_CUSTOM_DOMAIN", "")

        # Extract account credentials from connection string if provided
        if self.connection_string:
            for part in self.connection_string.split(";"):
                if part.startswith("AccountKey=") and not self.account_key:
                    self.account_key = part.split("=", 1)[1]
                elif part.startswith("AccountName=") and not self.account_name:
                    self.account_name = part.split("=", 1)[1]
            self._service_client = BlobServiceClient.from_connection_string(self.connection_string)
        elif self.account_name and self.account_key:
            account_url = f"https://{self.account_name}.blob.core.windows.net"
            self._service_client = BlobServiceClient(
                account_url=account_url,
                credential=self.account_key,
            )
        else:
            logger.warning("AzureBlobStorageService initialized without credentials.")
            account_url = f"https://{self.account_name or 'placeholder'}.blob.core.windows.net"
            self._service_client = BlobServiceClient(
                account_url=account_url,
                credential=self.account_key or "placeholder",
            )

        self._container_client = self._service_client.get_container_client(self.container_name)

    def upload_file(
        self,
        key: str,
        file_obj: IO,
        content_type: str,
        metadata: dict | None = None,
    ) -> str:
        from azure.storage.blob import ContentSettings

        safe_key = key.lstrip("/")
        try:
            blob_client = self._service_client.get_blob_client(
                container=self.container_name,
                blob=safe_key,
            )
            content_settings = ContentSettings(content_type=content_type)
            str_metadata = {str(k): str(v) for k, v in metadata.items()} if metadata else None

            if hasattr(file_obj, "seek"):
                file_obj.seek(0)

            blob_client.upload_blob(
                file_obj,
                overwrite=True,
                content_settings=content_settings,
                metadata=str_metadata,
            )
            logger.info("Uploaded file to Azure Blob Storage: %s", safe_key)
            return safe_key
        except Exception as exc:
            logger.error("Failed to upload file to Azure %s: %s", safe_key, exc)
            raise

    def generate_signed_url(
        self,
        key: str,
        expiry_seconds: int = 3600,
        response_content_type: str | None = None,
        download_filename: str | None = None,
    ) -> str:
        from azure.storage.blob import BlobSasPermissions, generate_blob_sas

        safe_key = key.lstrip("/")
        try:
            sas_kwargs = {
                "account_name": self.account_name,
                "container_name": self.container_name,
                "blob_name": safe_key,
                "account_key": self.account_key,
                "permission": BlobSasPermissions(read=True),
                "expiry": datetime.now(timezone.utc) + timedelta(seconds=expiry_seconds),
            }
            if response_content_type:
                sas_kwargs["content_type"] = response_content_type
            if download_filename:
                sas_kwargs["content_disposition"] = f'attachment; filename="{download_filename}"'

            sas_token = generate_blob_sas(**sas_kwargs)

            if self.custom_domain:
                base_url = f"https://{self.custom_domain.rstrip('/')}/{self.container_name}/{safe_key}"
            else:
                blob_client = self._service_client.get_blob_client(
                    container=self.container_name,
                    blob=safe_key,
                )
                base_url = blob_client.url

            url = f"{base_url}?{sas_token}"
            logger.debug("Generated SAS URL for Azure blob %s (expires in %ds)", safe_key, expiry_seconds)
            return url
        except Exception as exc:
            logger.error("Failed to generate SAS URL for Azure blob %s: %s", safe_key, exc)
            raise

    def delete_file(self, key: str) -> None:
        safe_key = key.lstrip("/")
        try:
            blob_client = self._service_client.get_blob_client(
                container=self.container_name,
                blob=safe_key,
            )
            blob_client.delete_blob()
            logger.info("Deleted file from Azure Blob Storage: %s", safe_key)
        except Exception as exc:
            logger.error("Failed to delete file from Azure %s: %s", safe_key, exc)
            raise

    def file_exists(self, key: str) -> bool:
        safe_key = key.lstrip("/")
        try:
            blob_client = self._service_client.get_blob_client(
                container=self.container_name,
                blob=safe_key,
            )
            return blob_client.exists()
        except Exception:
            return False

    def get_file_size(self, key: str) -> int:
        safe_key = key.lstrip("/")
        try:
            blob_client = self._service_client.get_blob_client(
                container=self.container_name,
                blob=safe_key,
            )
            properties = blob_client.get_blob_properties()
            return getattr(properties, "size", 0) or 0
        except Exception:
            return 0
