"""MinIO storage backend (S3-compatible, local development)."""
from .s3 import S3StorageService


class MinIOStorageService(S3StorageService):
    """
    MinIO is S3-compatible — inherits all S3 logic.
    The difference is that STORAGE_BACKEND=minio sets S3_ENDPOINT_URL
    to the MinIO server URL (e.g. http://minio:9000).
    No code changes needed vs S3 — only configuration differs.
    """
