"""Unit tests for the Google Drive storage backend.

These tests use unittest.mock to patch the Drive API client, so no real
credentials or network connections are required.  Google client libraries
are NOT required to be installed — the test file stubs them in sys.modules
so the importer never tries to resolve the real packages.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
import types
import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch, PropertyMock

# ---------------------------------------------------------------------------
# Stub out google/googleapiclient before any app import touches them.
# This lets the tests run without 'pip install google-api-python-client'.
# ---------------------------------------------------------------------------

def _make_stub_module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


for _pkg in [
    "google",
    "google.auth",
    "google.oauth2",
    "google.oauth2.service_account",
    "googleapiclient",
    "googleapiclient.discovery",
    "googleapiclient.http",
]:
    if _pkg not in sys.modules:
        _make_stub_module(_pkg)

# Provide the symbols the production code actually imports
sys.modules["google.oauth2.service_account"].Credentials = MagicMock()  # type: ignore[attr-defined]
sys.modules["google.auth"].default = MagicMock(return_value=(MagicMock(), None))  # type: ignore[attr-defined]
sys.modules["googleapiclient.discovery"].build = MagicMock(return_value=MagicMock())  # type: ignore[attr-defined]
sys.modules["googleapiclient.http"].MediaIoBaseUpload = MagicMock  # type: ignore[attr-defined]
sys.modules["googleapiclient.http"].MediaIoBaseDownload = MagicMock  # type: ignore[attr-defined]



# ---------------------------------------------------------------------------
# Helpers – build a minimal settings stub so we can instantiate the backend
# without a full Django setup.
# ---------------------------------------------------------------------------


class _FakeSettings:
    SECRET_KEY = "test-secret-key-for-unit-tests"
    GDRIVE_ROOT_FOLDER_ID = "root-folder-id-abc123"
    GDRIVE_SHARED_DRIVE_ID = ""
    GDRIVE_SERVICE_ACCOUNT_JSON = ""
    GDRIVE_SERVICE_ACCOUNT_INFO = ""
    PLATFORM_URL = "http://localhost:8000"


def _make_backend(
    root_folder_id: str = "root-folder-id-abc123",
    shared_drive_id: str = "",
) -> "GoogleDriveStorageService":  # noqa: F821
    """Instantiate GoogleDriveStorageService with all Drive API calls mocked."""
    with (
        patch("apps.storage.gdrive.settings", _FakeSettings()),
        patch("apps.storage.gdrive.GoogleDriveStorageService._build_credentials", return_value=MagicMock()),
        patch("apps.storage.gdrive.GoogleDriveStorageService._build_service", return_value=_build_mock_drive()),
    ):
        from apps.storage.gdrive import GoogleDriveStorageService

        svc = GoogleDriveStorageService.__new__(GoogleDriveStorageService)
        svc._credentials = MagicMock()
        svc._drive = _build_mock_drive()
        svc._root_folder_id = root_folder_id
        svc._shared_drive_id = shared_drive_id
        svc._folder_cache = {}
        return svc


def _build_mock_drive() -> MagicMock:
    """Return a mock that mimics the Drive v3 resource."""
    drive = MagicMock()

    # Default: file/folder search returns nothing
    list_resp = MagicMock()
    list_resp.execute.return_value = {"files": []}
    drive.files.return_value.list.return_value = list_resp

    # Default: file create returns a new ID
    create_resp = MagicMock()
    create_resp.execute.return_value = {"id": "new-file-id-xyz"}
    drive.files.return_value.create.return_value = create_resp

    # Default: file update returns an ID
    update_resp = MagicMock()
    update_resp.execute.return_value = {"id": "updated-file-id-xyz"}
    drive.files.return_value.update.return_value = update_resp

    # Default: file get returns size
    get_resp = MagicMock()
    get_resp.execute.return_value = {"size": "1024"}
    drive.files.return_value.get.return_value = get_resp

    # Default: delete returns nothing
    delete_resp = MagicMock()
    delete_resp.execute.return_value = None
    drive.files.return_value.delete.return_value = delete_resp

    return drive


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


class TestGoogleDriveStorageServiceInit(unittest.TestCase):
    """Tests for correct initialisation and configuration validation."""

    def test_raises_when_root_folder_id_missing(self):
        """If GDRIVE_ROOT_FOLDER_ID is empty the constructor should raise ValueError."""
        fake_settings = _FakeSettings()
        fake_settings.GDRIVE_ROOT_FOLDER_ID = ""

        with (
            patch("apps.storage.gdrive.settings", fake_settings),
            patch("apps.storage.gdrive.GoogleDriveStorageService._build_credentials", return_value=MagicMock()),
            patch("apps.storage.gdrive.GoogleDriveStorageService._build_service", return_value=_build_mock_drive()),
            self.assertRaises(ValueError),
        ):
            from apps.storage.gdrive import GoogleDriveStorageService
            GoogleDriveStorageService()

    def test_raises_when_google_libraries_missing(self):
        """ImportError is raised when google-api-python-client is not installed."""
        import builtins
        real_import = builtins.__import__

        def _blocked_import(name, *args, **kwargs):
            if name.startswith("google"):
                raise ImportError("Mocked missing google library")
            return real_import(name, *args, **kwargs)

        # Only test the _build_credentials path
        with patch("builtins.__import__", side_effect=_blocked_import):
            from apps.storage import gdrive as gdrive_module
            svc = gdrive_module.GoogleDriveStorageService.__new__(
                gdrive_module.GoogleDriveStorageService
            )
            with self.assertRaises(ImportError):
                # _build_credentials calls `from google.oauth2 import service_account`
                gdrive_module.GoogleDriveStorageService._build_credentials(svc)

    def test_reads_root_folder_id_from_settings(self):
        svc = _make_backend(root_folder_id="my-root-folder")
        self.assertEqual(svc._root_folder_id, "my-root-folder")


class TestGoogleDriveStorageServiceUpload(unittest.TestCase):
    """Tests for upload_file."""

    def test_upload_new_file_returns_key(self):
        svc = _make_backend()
        fake_file = BytesIO(b"hello world")
        result = svc.upload_file("courses/123/video.mp4", fake_file, "video/mp4")
        self.assertEqual(result, "courses/123/video.mp4")

    def test_upload_strips_leading_slash_from_key(self):
        svc = _make_backend()
        fake_file = BytesIO(b"data")
        result = svc.upload_file("/courses/123/file.pdf", fake_file, "application/pdf")
        self.assertEqual(result, "courses/123/file.pdf")

    def test_upload_calls_drive_create_for_new_file(self):
        svc = _make_backend()
        fake_file = BytesIO(b"data")

        with patch.object(svc, "_find_file_id", return_value=None):
            with patch("googleapiclient.http.MediaIoBaseUpload", return_value=MagicMock()):
                svc.upload_file("folder/test.pdf", fake_file, "application/pdf")
                svc._drive.files.return_value.create.assert_called()

    def test_upload_calls_drive_update_for_existing_file(self):
        svc = _make_backend()
        fake_file = BytesIO(b"data")

        with patch.object(svc, "_find_file_id", return_value="existing-file-id"):
            with patch("googleapiclient.http.MediaIoBaseUpload", return_value=MagicMock()):
                svc.upload_file("folder/test.pdf", fake_file, "application/pdf")
                svc._drive.files.return_value.update.assert_called()

    def test_upload_raises_on_drive_error(self):
        svc = _make_backend()
        svc._drive.files.return_value.create.return_value.execute.side_effect = Exception("Drive API error")
        fake_file = BytesIO(b"data")

        with patch.object(svc, "_find_file_id", return_value=None):
            with patch("googleapiclient.http.MediaIoBaseUpload", return_value=MagicMock()):
                with self.assertRaises(Exception):
                    svc.upload_file("test.pdf", fake_file, "application/pdf")


class TestGoogleDriveStorageServiceSignedUrl(unittest.TestCase):
    """Tests for generate_signed_url."""

    def test_signed_url_contains_key_token_expires(self):
        svc = _make_backend()
        with patch("apps.storage.gdrive.settings", _FakeSettings()):
            url = svc.generate_signed_url("courses/123/video.mp4", expiry_seconds=3600)
        self.assertIn("key=courses%2F123%2Fvideo.mp4", url)
        self.assertIn("token=", url)
        self.assertIn("expires=", url)

    def test_signed_url_uses_platform_url(self):
        svc = _make_backend()
        with patch("apps.storage.gdrive.settings", _FakeSettings()):
            url = svc.generate_signed_url("file.pdf")
        self.assertTrue(url.startswith("http://localhost:8000/gdrive-media/"))

    def test_signed_url_includes_download_param(self):
        svc = _make_backend()
        with patch("apps.storage.gdrive.settings", _FakeSettings()):
            url = svc.generate_signed_url("file.pdf", download_filename="my_file.pdf")
        self.assertIn("download=my_file.pdf", url)

    def test_token_is_valid_hmac(self):
        """The token in the URL must be verifiable with the same HMAC logic."""
        svc = _make_backend()
        with patch("apps.storage.gdrive.settings", _FakeSettings()):
            url = svc.generate_signed_url("courses/video.mp4", expiry_seconds=3600)

        from urllib.parse import parse_qs, urlsplit
        qs = parse_qs(urlsplit(url).query)
        key = qs["key"][0]
        token = qs["token"][0]
        expires = qs["expires"][0]

        secret = _FakeSettings.SECRET_KEY.encode()
        msg = f"{key}:{expires}".encode()
        expected = hmac.new(secret, msg, hashlib.sha256).hexdigest()
        self.assertEqual(token, expected)


class TestGoogleDriveStorageServiceDeleteFile(unittest.TestCase):
    """Tests for delete_file."""

    def test_delete_existing_file(self):
        svc = _make_backend()
        with patch.object(svc, "_find_file_id", return_value="file-to-delete"):
            svc.delete_file("courses/video.mp4")
            svc._drive.files.return_value.delete.assert_called_once()

    def test_delete_nonexistent_file_is_safe(self):
        """Deleting a non-existent key should not raise; it logs a warning."""
        svc = _make_backend()
        with patch.object(svc, "_find_file_id", return_value=None):
            # Should not raise
            svc.delete_file("nonexistent/key.mp4")
            svc._drive.files.return_value.delete.assert_not_called()


class TestGoogleDriveStorageServiceFileExists(unittest.TestCase):
    """Tests for file_exists."""

    def test_file_exists_returns_true(self):
        svc = _make_backend()
        with patch.object(svc, "_find_file_id", return_value="some-id"):
            self.assertTrue(svc.file_exists("courses/video.mp4"))

    def test_file_exists_returns_false(self):
        svc = _make_backend()
        with patch.object(svc, "_find_file_id", return_value=None):
            self.assertFalse(svc.file_exists("nonexistent.mp4"))


class TestGoogleDriveStorageServiceGetFileSize(unittest.TestCase):
    """Tests for get_file_size."""

    def test_returns_size_for_existing_file(self):
        svc = _make_backend()
        with patch.object(svc, "_find_file_id", return_value="file-id"):
            size = svc.get_file_size("courses/video.mp4")
        self.assertEqual(size, 1024)

    def test_returns_zero_for_nonexistent_file(self):
        svc = _make_backend()
        with patch.object(svc, "_find_file_id", return_value=None):
            size = svc.get_file_size("nonexistent.mp4")
        self.assertEqual(size, 0)


class TestGoogleDriveStorageServiceBuildKey(unittest.TestCase):
    """Tests for the inherited build_key utility."""

    def test_build_key_produces_uuid_filename(self):
        svc = _make_backend()
        key = svc.build_key("courses/123", "lecture.mp4")
        self.assertTrue(key.startswith("courses/123/"))
        self.assertTrue(key.endswith(".mp4"))
        # UUID hex is 32 chars
        filename = key.split("/")[-1]
        self.assertEqual(len(filename), 32 + 4)  # 32 hex + '.mp4'


class TestGoogleDriveStorageServiceServiceFactory(unittest.TestCase):
    """Tests that the factory wires up the gdrive backend correctly."""

    def test_factory_returns_gdrive_backend(self):
        with (
            patch("apps.storage.service.settings") as mock_settings,
            patch("apps.storage.gdrive.settings", _FakeSettings()),
            patch("apps.storage.gdrive.GoogleDriveStorageService._build_credentials", return_value=MagicMock()),
            patch("apps.storage.gdrive.GoogleDriveStorageService._build_service", return_value=_build_mock_drive()),
        ):
            mock_settings.STORAGE_BACKEND = "gdrive"
            mock_settings.GDRIVE_ROOT_FOLDER_ID = "root-folder-id-abc123"
            mock_settings.GDRIVE_SHARED_DRIVE_ID = ""
            mock_settings.GDRIVE_SERVICE_ACCOUNT_JSON = ""
            mock_settings.GDRIVE_SERVICE_ACCOUNT_INFO = ""
            mock_settings.PLATFORM_URL = "http://localhost:8000"
            mock_settings.SECRET_KEY = "test-key"

            from apps.storage.service import get_storage_service, reset_storage_service
            reset_storage_service()
            svc = get_storage_service()
            from apps.storage.gdrive import GoogleDriveStorageService
            self.assertIsInstance(svc, GoogleDriveStorageService)
            reset_storage_service()

    def test_factory_raises_for_unknown_backend(self):
        with patch("apps.storage.service.settings") as mock_settings:
            mock_settings.STORAGE_BACKEND = "unknown_backend_xyz"
            from apps.storage.service import get_storage_service, reset_storage_service
            reset_storage_service()
            with self.assertRaises(ValueError) as ctx:
                get_storage_service()
            self.assertIn("gdrive", str(ctx.exception))
            reset_storage_service()


if __name__ == "__main__":
    unittest.main()
