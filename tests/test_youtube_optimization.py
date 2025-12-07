"""Tests for YouTube API optimization features.

Test categories:
- QuotaTracker tests
- Retry logic tests
- Optimized API method tests
"""

from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError


class TestQuotaTracker:
    """Tests for QuotaTracker class."""

    def test_track_usage(self):
        """Test tracking API usage."""
        from app.youtube.quota import QuotaTracker

        tracker = QuotaTracker()

        # Track some operations
        tracker.track("videos.list", 1)
        tracker.track("search.list", 1)
        tracker.track("channels.list", 2)

        usage = tracker.get_daily_usage()
        # videos.list=1, search.list=100, channels.list=1*2=2
        assert usage == 1 + 100 + 2

    def test_get_remaining_quota(self):
        """Test remaining quota calculation."""
        from app.youtube.quota import QuotaTracker

        tracker = QuotaTracker(daily_limit=10000)

        # Track some usage
        tracker.track("videos.insert", 1)  # 1600 units

        remaining = tracker.get_remaining_quota()
        assert remaining == 10000 - 1600

    def test_can_perform_operation(self):
        """Test checking if operation can be performed."""
        from app.youtube.quota import QuotaTracker

        tracker = QuotaTracker(daily_limit=100)

        # Can perform small operation
        assert tracker.can_perform("videos.list") is True

        # Cannot perform expensive operation that exceeds limit
        assert tracker.can_perform("videos.insert") is False

    def test_get_usage_summary(self):
        """Test getting usage summary."""
        from app.youtube.quota import QuotaTracker

        tracker = QuotaTracker()
        tracker.track("videos.list", 5)
        tracker.track("search.list", 2)

        summary = tracker.get_usage_summary()

        assert "total_used" in summary
        assert "daily_limit" in summary
        assert "remaining" in summary
        assert "breakdown" in summary
        assert summary["total_used"] == 5 * 1 + 2 * 100

    def test_quota_costs(self):
        """Test that quota costs are correctly defined."""
        from app.youtube.quota import QuotaTracker

        assert QuotaTracker.QUOTA_COSTS["videos.insert"] == 1600
        assert QuotaTracker.QUOTA_COSTS["search.list"] == 100
        assert QuotaTracker.QUOTA_COSTS["videos.list"] == 1
        assert QuotaTracker.QUOTA_COSTS["playlistItems.list"] == 1


class TestRetryLogic:
    """Tests for retry logic helper functions."""

    def test_is_retryable_error_quota_exceeded(self):
        """Test that quota exceeded error is retryable."""
        from app.youtube.service import _is_retryable_error

        # Create mock HttpError for quota exceeded
        mock_resp = MagicMock()
        mock_resp.status = 403
        error_content = b'{"error": {"errors": [{"reason": "quotaExceeded"}]}}'

        error = HttpError(mock_resp, error_content)
        assert _is_retryable_error(error) is True

    def test_is_retryable_error_rate_limit(self):
        """Test that rate limit error is retryable."""
        from app.youtube.service import _is_retryable_error

        # Create mock HttpError for rate limit
        mock_resp = MagicMock()
        mock_resp.status = 429
        error_content = b'{"error": {"errors": [{"reason": "rateLimitExceeded"}]}}'

        error = HttpError(mock_resp, error_content)
        assert _is_retryable_error(error) is True

    def test_is_retryable_error_auth_error(self):
        """Test that auth error is NOT retryable."""
        from app.youtube.service import _is_retryable_error

        # Create mock HttpError for auth error
        mock_resp = MagicMock()
        mock_resp.status = 401
        error_content = b'{"error": {"errors": [{"reason": "unauthorized"}]}}'

        error = HttpError(mock_resp, error_content)
        assert _is_retryable_error(error) is False

    def test_is_retryable_error_permission_denied(self):
        """Test that permission denied (403 non-quota) is NOT retryable."""
        from app.youtube.service import _is_retryable_error

        # Create mock HttpError for forbidden (permission) error
        mock_resp = MagicMock()
        mock_resp.status = 403
        error_content = b'{"error": {"errors": [{"reason": "forbidden"}]}}'

        error = HttpError(mock_resp, error_content)
        assert _is_retryable_error(error) is False


class TestYouTubeServiceOptimization:
    """Tests for optimized YouTube service methods."""

    @pytest.fixture
    def mock_youtube_service(self):
        """Create a mock YouTube service."""
        from unittest.mock import MagicMock

        from google.oauth2.credentials import Credentials

        with patch("app.youtube.service.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service

            # Create mock credentials
            mock_creds = MagicMock(spec=Credentials)

            from app.youtube.service import YouTubeService

            service = YouTubeService(mock_creds)
            service._mock_api = mock_service
            yield service

    def test_check_video_exists_on_youtube_found(self, mock_youtube_service):
        """Test checking video exists returns True when found."""
        mock_youtube_service._mock_api.videos().list().execute.return_value = {
            "items": [{"id": "test-video-id"}]
        }

        result = mock_youtube_service.check_video_exists_on_youtube("test-video-id")
        assert result is True

    def test_check_video_exists_on_youtube_not_found(self, mock_youtube_service):
        """Test checking video exists returns False when not found."""
        mock_youtube_service._mock_api.videos().list().execute.return_value = {
            "items": []
        }

        result = mock_youtube_service.check_video_exists_on_youtube("nonexistent")
        assert result is False

    def test_get_videos_batch_empty_list(self, mock_youtube_service):
        """Test batch get with empty list returns empty."""
        result = mock_youtube_service.get_videos_batch([])
        assert result == []

    def test_get_videos_batch_max_50(self, mock_youtube_service):
        """Test batch get limits to 50 videos."""
        mock_youtube_service._mock_api.videos().list().execute.return_value = {
            "items": [{"id": f"video-{i}"} for i in range(50)]
        }

        # Pass more than 50 IDs
        video_ids = [f"video-{i}" for i in range(100)]
        result = mock_youtube_service.get_videos_batch(video_ids)

        # Should only return max 50
        assert len(result) <= 50

    def test_list_my_videos_optimized_uses_playlist_api(self, mock_youtube_service):
        """Test optimized list uses playlist API."""
        # Mock channel response with uploads playlist
        mock_youtube_service._mock_api.channels().list().execute.return_value = {
            "items": [
                {
                    "contentDetails": {
                        "relatedPlaylists": {"uploads": "UU123456"}
                    }
                }
            ]
        }

        # Mock playlist items response
        mock_youtube_service._mock_api.playlistItems().list().execute.return_value = {
            "items": [{"snippet": {"title": "Test Video"}}]
        }

        result = mock_youtube_service.list_my_videos_optimized(25)

        # Verify playlistItems was called
        mock_youtube_service._mock_api.playlistItems().list.assert_called()
        assert len(result) == 1


class TestQuotaSingleton:
    """Test quota tracker singleton behavior."""

    def test_get_quota_tracker_returns_same_instance(self):
        """Test that get_quota_tracker returns singleton."""
        from app.youtube import quota

        # Reset singleton for test
        quota._quota_tracker = None

        tracker1 = quota.get_quota_tracker()
        tracker2 = quota.get_quota_tracker()

        assert tracker1 is tracker2
