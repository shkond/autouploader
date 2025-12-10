"""Unit tests for YouTube routes.

Tests for:
- Get channel info endpoint
- List videos endpoint
- Upload video endpoint
- Quota status endpoint
- Check video exists endpoint
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient


@pytest.fixture
def mock_youtube_service():
    """Mock YouTube service for tests."""
    service = MagicMock()
    service.get_channel_info.return_value = {
        "id": "channel123",
        "snippet": {
            "title": "Test Channel",
            "description": "A test channel",
        },
        "statistics": {
            "viewCount": "1000",
            "subscriberCount": "100",
            "videoCount": "10",
        },
    }
    service.list_my_videos.return_value = []
    service.check_video_exists_on_youtube.return_value = True
    service.upload_from_drive_async = AsyncMock()
    return service


@pytest.fixture
def mock_credentials():
    """Mock Google credentials."""
    creds = MagicMock()
    creds.token = "mock-access-token"
    creds.valid = True
    creds.scopes = ["https://www.googleapis.com/auth/youtube"]
    return creds


@pytest.fixture
def mock_quota_tracker():
    """Mock quota tracker for tests."""
    with patch("app.youtube.routes.get_quota_tracker") as mock:
        tracker = MagicMock()
        tracker.get_usage_summary.return_value = {
            "date": "2025-12-08",
            "total_used": 1600,
            "daily_limit": 10000,
            "remaining": 8400,
            "usage_percentage": 16.0,
            "breakdown": {
                "videos.insert": {"calls": 1, "cost_per_call": 1600, "total_cost": 1600}
            },
        }
        mock.return_value = tracker
        yield tracker


@pytest.fixture
def test_client_with_mocks(mock_youtube_service, mock_credentials):
    """Create test client with mocked dependencies."""
    from app.core.dependencies import get_user_credentials, get_youtube_service
    from app.main import app

    # Override dependencies
    async def override_youtube_service():
        return mock_youtube_service

    async def override_credentials():
        return mock_credentials

    app.dependency_overrides[get_youtube_service] = override_youtube_service
    app.dependency_overrides[get_user_credentials] = override_credentials

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
class TestGetChannelInfo:
    """Tests for get channel info endpoint."""

    def test_get_channel_info_requires_auth(self, test_client):
        """Test that channel info requires authentication."""
        response = test_client.get("/youtube/channel")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_channel_info_success(self, mock_youtube_service, test_client_with_mocks):
        """Test getting channel info successfully."""
        response = test_client_with_mocks.get("/youtube/channel")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == "channel123"


@pytest.mark.unit
class TestListMyVideos:
    """Tests for list videos endpoint."""

    def test_list_my_videos_requires_auth(self, test_client):
        """Test that list videos requires authentication."""
        response = test_client.get("/youtube/videos")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_my_videos_success(self, mock_youtube_service, test_client_with_mocks):
        """Test listing videos successfully."""
        mock_youtube_service.list_my_videos.return_value = [
            {
                "id": {"videoId": "video123"},
                "snippet": {
                    "title": "Test Video",
                    "description": "A test video",
                    "thumbnails": {"default": {"url": "https://example.com/thumb.jpg"}},
                    "channelId": "channel123",
                    "publishedAt": "2025-01-01T00:00:00Z",
                },
            },
        ]

        response = test_client_with_mocks.get("/youtube/videos?max_results=10")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 1

    def test_list_my_videos_empty(self, mock_youtube_service, test_client_with_mocks):
        """Test listing when no videos exist."""
        mock_youtube_service.list_my_videos.return_value = []

        response = test_client_with_mocks.get("/youtube/videos")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []


@pytest.mark.unit
class TestUploadVideo:
    """Tests for upload video endpoint."""

    def test_upload_video_requires_auth(self, test_client):
        """Test that upload requires authentication."""
        response = test_client.post(
            "/youtube/upload",
            json={
                "drive_file_id": "file123",
                "metadata": {
                    "title": "Test Video",
                    "description": "Test",
                    "privacy_status": "private",
                },
            },
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_upload_video_success(self, mock_youtube_service, test_client_with_mocks):
        """Test uploading video successfully."""
        from app.youtube.schemas import UploadResult

        mock_result = UploadResult(
            success=True,
            video_id="youtube123",
            video_url="https://www.youtube.com/watch?v=youtube123",
            message="Upload completed successfully",
        )
        mock_youtube_service.upload_from_drive_async = AsyncMock(return_value=mock_result)

        response = test_client_with_mocks.post(
            "/youtube/upload",
            json={
                "drive_file_id": "file123",
                "metadata": {
                    "title": "Test Video",
                    "description": "Test description",
                    "privacy_status": "private",
                },
            },
        )

        assert response.status_code == status.HTTP_200_OK


@pytest.mark.unit
class TestQuotaStatus:
    """Tests for quota status endpoint."""

    def test_get_quota_status(self, test_client, mock_quota_tracker):
        """Test getting quota status."""
        response = test_client.get("/youtube/quota")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "total_used" in data
        assert "remaining" in data
        assert "daily_limit" in data

    def test_quota_status_breakdown(self, test_client, mock_quota_tracker):
        """Test quota breakdown is included."""
        response = test_client.get("/youtube/quota")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "breakdown" in data


@pytest.mark.unit
class TestCheckVideoExists:
    """Tests for check video exists endpoint."""

    def test_check_video_exists_requires_auth(self, test_client):
        """Test that check video exists requires authentication."""
        response = test_client.get("/youtube/video/video123/exists")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_check_video_exists_found(self, mock_youtube_service, test_client_with_mocks):
        """Test checking existing video."""
        mock_youtube_service.check_video_exists_on_youtube.return_value = True

        response = test_client_with_mocks.get("/youtube/video/video123/exists")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["exists"] is True
        assert data["video_id"] == "video123"

    def test_check_video_exists_not_found(self, mock_youtube_service, test_client_with_mocks):
        """Test checking non-existent video."""
        mock_youtube_service.check_video_exists_on_youtube.return_value = False

        response = test_client_with_mocks.get("/youtube/video/nonexistent/exists")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["exists"] is False

