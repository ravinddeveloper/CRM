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
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
            config=Config(signature_version="s3v4"),
        )
        if settings.S3_ENDPOINT_URL:
            kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL

        self._client = boto3.client("s3", **kwargs)
        self._bucket = settings.S3_BUCKET_NAME

    def upload_file(self, key: str, file_obj: IO, content_type: str, metadata: dict | None = None) -> str:
        extra_args = {"ContentType": content_type}
        if metadata:
            extra_args["Metadata"] = {str(k): str(v) for k, v in metadata.items()}

        try:
            self._client.upload_fileobj(
                file_obj,
                self._bucket,
                key,
                ExtraArgs=extra_args,
            )
            logger.info("Uploaded file to storage: %s", key)
            return key
        except Exception as exc:
            logger.error("Failed to upload file %s: %s", key, exc)
            raise

    def generate_signed_url(
        self,
        key: str,
        expiry_seconds: int = 3600,
        response_content_type: str | None = None,
        download_filename: str | None = None,
    ) -> str:
        params = {
            "Bucket": self._bucket,
            "Key": key,
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
        logger.debug("Generated signed URL for %s (expires in %ds)", key, expiry_seconds)
        return url

    def delete_file(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
            logger.info("Deleted file from storage: %s", key)
        except Exception as exc:
            logger.error("Failed to delete file %s: %s", key, exc)
            raise

    def file_exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except Exception:
            return False

    def get_file_size(self, key: str) -> int:
        try:
            response = self._client.head_object(Bucket=self._bucket, Key=key)
            return response.get("ContentLength", 0)
        except Exception:
            return 0
