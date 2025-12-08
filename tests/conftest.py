"""Common test fixtures for DigitalOcean migration tests."""

import asyncio
import os
from collections.abc import AsyncGenerator, Generator
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base

# Test database URL (in-memory SQLite for fast tests)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Test encryption key (32 bytes for Fernet)
TEST_ENCRYPTION_KEY = "test-encryption-key-32-bytes!!"


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def test_engine():
    """Create a test database engine."""
    # Import models to register them with Base
    from app import models  # noqa: F401

    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def test_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async_session_maker = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    settings = MagicMock()
    settings.database_url = TEST_DATABASE_URL
    settings.async_database_url = TEST_DATABASE_URL
    settings.secret_key = TEST_ENCRYPTION_KEY
    settings.debug = True
    settings.app_env = "development"
    settings.max_concurrent_uploads = 2
    settings.google_client_id = "test-client-id"
    settings.google_client_secret = "test-client-secret"
    settings.google_redirect_uri = "http://localhost:8000/auth/callback"
    settings.scopes_list = ["scope1", "scope2"]
    return settings


@pytest.fixture
def sample_video_metadata() -> dict[str, Any]:
    """Create sample video metadata for testing."""
    return {
        "title": "Test Video",
        "description": "A test video description",
        "privacy_status": "private",
        "tags": ["test", "video"],
        "category_id": "22",
    }


@pytest.fixture
def sample_queue_job_data(sample_video_metadata) -> dict[str, Any]:
    """Create sample queue job data for testing."""
    import json

    return {
        "id": uuid4(),
        "drive_file_id": "test-drive-file-id",
        "drive_file_name": "test_video.mp4",
        "drive_md5_checksum": "abc123def456",
        "folder_path": "/test/folder",
        "batch_id": "batch-001",
        "metadata_json": json.dumps(sample_video_metadata),
        "status": "pending",
        "progress": 0.0,
        "message": "",
        "video_id": None,
        "video_url": None,
        "error": None,
        "retry_count": 0,
        "max_retries": 3,
    }


@pytest.fixture
def env_override():
    """Context manager for overriding environment variables."""
    def _override(**kwargs):
        return patch.dict(os.environ, kwargs, clear=False)
    return _override


@pytest.fixture
def clear_settings_cache():
    """Clear the settings cache before and after test."""
    from app.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ============================================================================
# Google API Mock Fixtures
# ============================================================================


@pytest.fixture
def mock_google_credentials():
    """Create mock Google OAuth credentials.
    
    Returns a MagicMock that simulates google.oauth2.credentials.Credentials
    with common attributes pre-configured for testing.
    """
    mock_creds = MagicMock()
    mock_creds.token = "mock-access-token"
    mock_creds.refresh_token = "mock-refresh-token"
    mock_creds.expired = False
    mock_creds.valid = True
    mock_creds.scopes = [
        "https://www.googleapis.com/auth/youtube",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    mock_creds.expiry = None
    return mock_creds


@pytest.fixture
def mock_drive_service(mock_google_credentials):
    """Create mock Google Drive service.
    
    Patches DriveService and returns a mock that can be configured
    to return specific values for testing Drive operations.
    """
    with patch("app.drive.service.DriveService") as mock_class:
        service = MagicMock()

        # Default return values for common methods
        service.list_files.return_value = []
        service.get_file_metadata.return_value = {
            "id": "test-file-id",
            "name": "test_video.mp4",
            "mimeType": "video/mp4",
            "size": "1048576",
            "md5Checksum": "abc123def456",
        }
        service.get_folder_path.return_value = "/Test Folder"

        mock_class.return_value = service
        yield service


@pytest.fixture
def mock_youtube_service(mock_google_credentials):
    """Create mock YouTube service.
    
    Patches YouTubeService and returns a mock that can be configured
    to return specific values for testing YouTube operations.
    """
    with patch("app.youtube.service.YouTubeService") as mock_class:
        service = MagicMock()

        # Default return values for common methods
        service.get_channel_info.return_value = {
            "id": "test-channel-id",
            "snippet": {"title": "Test Channel"},
            "statistics": {"videoCount": "10"},
        }
        service.list_my_videos.return_value = []
        service.check_video_exists_on_youtube.return_value = True

        # Mock successful upload result
        from app.youtube.schemas import UploadResult
        service.upload_from_drive.return_value = UploadResult(
            success=True,
            video_id="test-video-id",
            video_url="https://www.youtube.com/watch?v=test-video-id",
            message="Upload completed successfully",
        )
        service.upload_from_drive_with_retry.return_value = service.upload_from_drive.return_value

        mock_class.return_value = service
        yield service


@pytest.fixture
def mock_quota_tracker():
    """Create mock quota tracker.
    
    Returns a mock QuotaTracker with configurable quota limits and usage.
    """
    with patch("app.youtube.quota.get_quota_tracker") as mock_getter:
        tracker = MagicMock()
        tracker.get_remaining_quota.return_value = 8400
        tracker.get_daily_usage.return_value = 1600
        tracker.can_perform.return_value = True
        tracker.get_usage_summary.return_value = {
            "date": "2025-12-08",
            "total_used": 1600,
            "daily_limit": 10000,
            "remaining": 8400,
            "usage_percentage": 16.0,
            "breakdown": {},
        }
        mock_getter.return_value = tracker
        yield tracker


@pytest_asyncio.fixture
async def async_http_client():
    """Create async HTTP test client.
    
    Provides an httpx AsyncClient configured for the FastAPI app,
    suitable for testing async endpoints.
    """
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def test_video_file(tmp_path):
    """Create a test video file.
    
    Creates a minimal mock video file in a temporary directory
    for testing file operations without requiring actual video content.
    
    Returns:
        Path to the temporary test video file
    """
    video_path = tmp_path / "test_video.mp4"
    # Create a minimal "video" file (not actually valid video data)
    video_path.write_bytes(b"\x00" * 1024)  # 1KB dummy file
    return video_path

