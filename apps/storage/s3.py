"""S3/MinIO storage backend using boto3."""
import logging
from typing import IO

from django.conf import settings

from .base import BaseStorageService

logger = logging.getLogger("apps.storage")


class S3StorageService(BaseStorageService):
    """Storage backend for AWS S3 (and S3-compatible like MinIO)."""

    def __init__(self):
        import boto3
        from botocore.config import Config

        kwargs = dict(
            region_name=getattr(settings, "S3_REGION", "us-east-1"),
            config=Config(signature_version="s3v4"),
        )
        access_key = getattr(settings, "S3_ACCESS_KEY", None)
        secret_key = getattr(settings, "S3_SECRET_KEY", None)
        endpoint_url = getattr(settings, "S3_ENDPOINT_URL", None)

        if access_key:
            kwargs["aws_access_key_id"] = access_key
        if secret_key:
            kwargs["aws_secret_access_key"] = secret_key
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url

        self._client = boto3.client("s3", **kwargs)
        self._bucket = getattr(settings, "S3_BUCKET_NAME", "lms-content")

    def upload_file(self, key: str, file_obj: IO, content_type: str, metadata: dict | None = None) -> str:
        safe_key = key.lstrip("/")
        extra_args = {"ContentType": content_type}
        if metadata:
            extra_args["Metadata"] = {str(k): str(v) for k, v in metadata.items()}

        if hasattr(file_obj, "seek"):
            file_obj.seek(0)

        try:
            self._client.upload_fileobj(
                file_obj,
                self._bucket,
                safe_key,
                ExtraArgs=extra_args,
            )
            logger.info("Uploaded file to storage: %s", safe_key)
            return safe_key
        except Exception as exc:
            logger.error("Failed to upload file %s: %s", safe_key, exc)
            raise

    def generate_signed_url(
        self,
        key: str,
        expiry_seconds: int = 3600,
        response_content_type: str | None = None,
        download_filename: str | None = None,
    ) -> str:
        safe_key = key.lstrip("/")
        params = {
            "Bucket": self._bucket,
            "Key": safe_key,
        }
        if response_content_type:
            params["ResponseContentType"] = response_content_type
        if download_filename:
            params["ResponseContentDisposition"] = f'attachment; filename="{download_filename}"'

        url = self._client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=expiry_seconds,
        )
        logger.debug("Generated signed URL for %s (expires in %ds)", safe_key, expiry_seconds)
        return url

    def delete_file(self, key: str) -> None:
        safe_key = key.lstrip("/")
        try:
            self._client.delete_object(Bucket=self._bucket, Key=safe_key)
            logger.info("Deleted file from storage: %s", safe_key)
        except Exception as exc:
            logger.error("Failed to delete file %s: %s", safe_key, exc)
            raise

    def file_exists(self, key: str) -> bool:
        safe_key = key.lstrip("/")
        try:
            self._client.head_object(Bucket=self._bucket, Key=safe_key)
            return True
        except Exception:
            return False

    def get_file_size(self, key: str) -> int:
        safe_key = key.lstrip("/")
        try:
            response = self._client.head_object(Bucket=self._bucket, Key=safe_key)
            return response.get("ContentLength", 0)
        except Exception:
            return 0
