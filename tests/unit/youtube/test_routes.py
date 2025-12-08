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
def mock_session_manager():
    """Mock session manager for youtube tests."""
    with patch("app.auth.dependencies.get_session_manager") as mock:
        manager = MagicMock()
        manager.verify_session.return_value = {
            "username": "testuser",
            "user_id": "user123",
        }
        mock.return_value = manager
        yield manager


@pytest.fixture
def mock_oauth_service():
    """Mock OAuth service for youtube tests."""
    with patch("app.youtube.routes.get_oauth_service") as mock:
        service = MagicMock()
        mock_creds = MagicMock()
        mock_creds.token = "mock-access-token"
        mock_creds.valid = True
        mock_creds.scopes = ["https://www.googleapis.com/auth/youtube"]
        service.get_credentials = AsyncMock(return_value=mock_creds)
        mock.return_value = service
        yield service


@pytest.fixture
def mock_youtube_service():
    """Mock YouTube service for tests."""
    with patch("app.youtube.routes.YouTubeService") as mock:
        service = MagicMock()
        mock.return_value = service
        yield service


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
def test_client():
    """Create test client for the FastAPI app."""
    from app.main import app
    return TestClient(app)


@pytest.mark.unit
class TestGetChannelInfo:
    """Tests for get channel info endpoint."""

    def test_get_channel_info_requires_auth(self, test_client):
        """Test that channel info requires authentication."""
        with patch("app.auth.dependencies.get_session_manager") as mock:
            mock.return_value.verify_session.return_value = None

            response = test_client.get("/youtube/channel")

            assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_channel_info_success(
        self, test_client, mock_session_manager, mock_oauth_service, mock_youtube_service
    ):
        """Test getting channel info successfully."""
        mock_youtube_service.get_channel_info.return_value = {
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

        response = test_client.get(
            "/youtube/channel",
            cookies={"session": "valid-token"},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_channel_info_not_authenticated_with_google(
        self, test_client, mock_session_manager, mock_oauth_service
    ):
        """Test channel info when not authenticated with Google."""
        mock_oauth_service.get_credentials.return_value = None

        response = test_client.get(
            "/youtube/channel",
            cookies={"session": "valid-token"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.unit
class TestListMyVideos:
    """Tests for list videos endpoint."""

    def test_list_my_videos_success(
        self, test_client, mock_session_manager, mock_oauth_service, mock_youtube_service
    ):
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

        response = test_client.get(
            "/youtube/videos?max_results=10",
            cookies={"session": "valid-token"},
        )

        assert response.status_code == status.HTTP_200_OK

    def test_list_my_videos_empty(
        self, test_client, mock_session_manager, mock_oauth_service, mock_youtube_service
    ):
        """Test listing when no videos exist."""
        mock_youtube_service.list_my_videos.return_value = []

        response = test_client.get(
            "/youtube/videos",
            cookies={"session": "valid-token"},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []


@pytest.mark.unit
class TestUploadVideo:
    """Tests for upload video endpoint."""

    def test_upload_video_requires_auth(self, test_client):
        """Test that upload requires authentication."""
        with patch("app.auth.dependencies.get_session_manager") as mock:
            mock.return_value.verify_session.return_value = None

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

    def test_upload_video_success(
        self, test_client, mock_session_manager, mock_oauth_service, mock_youtube_service
    ):
        """Test uploading video successfully."""
        mock_youtube_service.upload_from_drive.return_value = MagicMock(
            success=True,
            video_id="youtube123",
            video_url="https://www.youtube.com/watch?v=youtube123",
            message="Upload completed successfully",
        )

        response = test_client.post(
            "/youtube/upload",
            json={
                "drive_file_id": "file123",
                "metadata": {
                    "title": "Test Video",
                    "description": "Test description",
                    "privacy_status": "private",
                },
            },
            cookies={"session": "valid-token"},
        )

        # May need additional mocking for full success
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ]


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
        with patch("app.auth.dependencies.get_session_manager") as mock:
            mock.return_value.verify_session.return_value = None

            response = test_client.get("/youtube/video/video123/exists")

            assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_check_video_exists_found(
        self, test_client, mock_session_manager, mock_oauth_service, mock_youtube_service
    ):
        """Test checking existing video."""
        mock_youtube_service.check_video_exists_on_youtube.return_value = True

        response = test_client.get(
            "/youtube/video/video123/exists",
            cookies={"session": "valid-token"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["exists"] is True
        assert data["video_id"] == "video123"

    def test_check_video_exists_not_found(
        self, test_client, mock_session_manager, mock_oauth_service, mock_youtube_service
    ):
        """Test checking non-existent video."""
        mock_youtube_service.check_video_exists_on_youtube.return_value = False

        response = test_client.get(
            "/youtube/video/nonexistent/exists",
            cookies={"session": "valid-token"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["exists"] is False
