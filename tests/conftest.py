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
    return {
        "id": uuid4(),
        "drive_file_id": "test-drive-file-id",
        "drive_file_name": "test_video.mp4",
        "drive_md5_checksum": "abc123def456",
        "folder_path": "/test/folder",
        "batch_id": "batch-001",
        "metadata_json": str(sample_video_metadata),
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
