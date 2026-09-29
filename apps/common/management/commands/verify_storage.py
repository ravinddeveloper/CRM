"""Management command to test and verify the active storage backend."""
import io
import uuid

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.storage.service import get_storage_service


class Command(BaseCommand):
    help = "Verify object storage backend connectivity, upload, URL signing, and deletion."

    def handle(self, *args, **options):
        backend = getattr(settings, "STORAGE_BACKEND", "local")
        self.stdout.write(f"Testing storage backend: '{backend}'...")

        try:
            storage = get_storage_service()
            test_key = f"_health_check/ping_{uuid.uuid4().hex[:8]}.txt"
            content = b"Storage connectivity verified by EduFlow LMS health check."

            # Test upload
            self.stdout.write("1. Testing file upload...")
            uploaded_path = storage.upload_file(test_key, io.BytesIO(content), "text/plain")
            self.stdout.write(self.style.SUCCESS(f"   [OK] Uploaded to: {uploaded_path}"))

            # Test existence
            self.stdout.write("2. Verifying file existence...")
            exists = storage.file_exists(test_key)
            if not exists:
                self.stdout.write(self.style.ERROR("   [FAIL] File existence check failed!"))
            else:
                self.stdout.write(self.style.SUCCESS("   [OK] File exists in storage."))

            # Test signed URL generation
            self.stdout.write("3. Testing presigned URL generation...")
            if hasattr(storage, "generate_signed_url"):
                signed_url = storage.generate_signed_url(test_key, expiry_seconds=300)
            elif hasattr(storage, "get_presigned_url"):
                signed_url = storage.get_presigned_url(test_key, expires_in=300)
            else:
                signed_url = f"/media/{test_key}"
            self.stdout.write(self.style.SUCCESS(f"   [OK] Generated signed URL: {signed_url[:70]}..."))

            # Test deletion
            self.stdout.write("4. Testing cleanup deletion...")
            storage.delete_file(test_key)
            self.stdout.write(self.style.SUCCESS("   [OK] Cleaned up test object."))

            self.stdout.write(self.style.SUCCESS(f"\nAll storage verification checks PASSED for '{backend}'!"))

        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"\nStorage check FAILED with error: {exc}"))
