"""Unit tests for Google Drive routes.

Tests for:
- List files endpoint
- Scan folder endpoint
- Get file info endpoint
- Upload folder endpoint
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.drive.schemas import DriveFile, FileType


@pytest.fixture
def mock_drive_service():
    """Mock Drive service for tests."""
    service = MagicMock()
    # Mock async methods with AsyncMock
    service.list_files = AsyncMock(return_value=[])
    service.scan_folder = AsyncMock()
    service.get_file_metadata = AsyncMock(return_value={})
    service.get_folder_info = AsyncMock(return_value={})
    service.get_all_videos_flat = AsyncMock(return_value=[])
    return service


@pytest.fixture
def mock_queue_repo():
    """Mock Queue repository for tests."""
    repo = MagicMock()
    repo.is_file_id_in_queue = AsyncMock(return_value=False)
    repo.is_md5_in_queue = AsyncMock(return_value=False)
    repo.add_job = AsyncMock()
    return repo


@pytest.fixture
def test_client_with_mocks(mock_drive_service, mock_queue_repo):
    """Create test client with mocked dependencies."""
    from app.core.dependencies import get_drive_service, get_user_id_from_session
    from app.database import get_db
    from app.main import app

    # Override dependencies
    async def override_drive_service():
        return mock_drive_service

    async def override_user_id():
        return "test_user_123"

    async def override_db():
        session = MagicMock()
        session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        yield session

    app.dependency_overrides[get_drive_service] = override_drive_service
    app.dependency_overrides[get_user_id_from_session] = override_user_id
    app.dependency_overrides[get_db] = override_db

    client = TestClient(app)
    yield client

    # Clean up overrides
    app.dependency_overrides.clear()


@pytest.fixture
def test_client():
    """Create test client for the FastAPI app."""
    from app.main import app
    return TestClient(app)


@pytest.mark.unit
class TestListFiles:
    """Tests for list files endpoint."""

    @staticmethod
    def test_list_files_requires_auth(test_client):
        """Test that list files requires authentication."""
        # No session cookie = should get 401
        response = test_client.get("/drive/files")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @staticmethod
    def test_list_files_success(mock_drive_service, test_client_with_mocks):
        """Test successful file listing."""
        mock_drive_service.list_files = AsyncMock(return_value=[
            DriveFile(
                id="file1",
                name="video1.mp4",
                mimeType="video/mp4",
                size=1024,
                file_type=FileType.VIDEO,
            ),
            DriveFile(
                id="file2",
                name="video2.mp4",
                mimeType="video/mp4",
                size=2048,
                file_type=FileType.VIDEO,
            ),
        ])

        response = test_client_with_mocks.get("/drive/files?folder_id=root&video_only=true")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 2

    @staticmethod
    def test_list_files_empty_folder(mock_drive_service, test_client_with_mocks):
        """Test listing empty folder."""
        mock_drive_service.list_files = AsyncMock(return_value=[])

        response = test_client_with_mocks.get("/drive/files?folder_id=empty-folder")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []


@pytest.mark.unit
class TestScanFolder:
    """Tests for scan folder endpoint."""

    @staticmethod
    def test_scan_folder_success(mock_drive_service, test_client_with_mocks):
        """Test successful folder scan."""
        from app.drive.schemas import DriveFolder

        mock_drive_service.scan_folder = AsyncMock(return_value=DriveFolder(
            id="folder123",
            name="Test Folder",
            files=[],
            subfolders=[],
            total_videos=1,
        ))

        response = test_client_with_mocks.post(
            "/drive/scan",
            json={"folder_id": "folder123", "recursive": False},
        )

        assert response.status_code == status.HTTP_200_OK

    @staticmethod
    def test_scan_folder_requires_auth(test_client):
        """Test that folder scan requires authentication."""
        response = test_client.post(
            "/drive/scan",
            json={"folder_id": "folder123"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.unit
class TestGetFileInfo:
    """Tests for get file info endpoint."""

    @staticmethod
    def test_get_file_info_success(mock_drive_service, test_client_with_mocks):
        """Test getting file info successfully."""
        mock_drive_service.get_file_metadata = AsyncMock(return_value={
            "id": "file123",
            "name": "test_video.mp4",
            "mimeType": "video/mp4",
            "size": "10485760",
            "md5Checksum": "abc123def456",
        })

        response = test_client_with_mocks.get("/drive/file/file123")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == "file123"

    @staticmethod
    def test_get_file_info_not_found(mock_drive_service, test_client_with_mocks):
        """Test file not found error."""
        import httplib2
        from googleapiclient.errors import HttpError

        mock_drive_service.get_file_metadata = AsyncMock(side_effect=HttpError(
            httplib2.Response({"status": 404}),
            b'{"error": {"message": "File not found"}}',
        ))

        response = test_client_with_mocks.get("/drive/file/nonexistent")

        assert response.status_code in [
            status.HTTP_404_NOT_FOUND,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ]


@pytest.mark.unit
class TestUploadFolder:
    """Tests for upload folder endpoint."""

    @staticmethod
    def test_upload_folder_requires_auth(test_client):
        """Test that upload folder requires authentication."""
        response = test_client.post(
            "/drive/folder/upload",
            json={
                "folder_id": "folder123",
                "settings": {
                    "title_template": "{filename}",
                    "description_template": "Auto-uploaded",
                    "default_privacy": "private",
                },
            },
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @staticmethod
    def test_upload_folder_empty_success(mock_drive_service, test_client_with_mocks):
        """Test folder upload with no videos."""
        mock_drive_service.get_folder_info = AsyncMock(return_value={"id": "folder123", "name": "My Videos"})
        mock_drive_service.get_all_videos_flat = AsyncMock(return_value=[])

        response = test_client_with_mocks.post(
            "/drive/folder/upload",
            json={
                "folder_id": "folder123",
                "settings": {
                    "title_template": "{filename}",
                    "description_template": "Auto-uploaded",
                    "default_privacy": "private",
                },
                "skip_duplicates": True,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["added_count"] == 0

