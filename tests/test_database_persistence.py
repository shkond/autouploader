"""Tests for database persistence and PostgreSQL migration.

Test categories:
1.1 PostgreSQL接続・設定テスト
1.2 マイグレーションテスト
"""

import os
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import Settings


class TestPostgreSQLConnection:
    """1.1 PostgreSQL接続・設定テスト"""

    @staticmethod
    def test_sqlite_connection_url():
        """Test SQLite connection URL conversion."""
        settings = Settings(
            database_url="sqlite:///./test.db",
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.async_database_url == "sqlite+aiosqlite:///./test.db"

    @staticmethod
    def test_postgresql_url_conversion_from_postgres():
        """Test postgres:// → postgresql+asyncpg:// conversion (Heroku style)."""
        settings = Settings(
            database_url="postgres://user:pass@host:5432/dbname",
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.async_database_url == "postgresql+asyncpg://user:pass@host:5432/dbname"

    @staticmethod
    def test_postgresql_url_conversion_from_postgresql():
        """Test postgresql:// → postgresql+asyncpg:// conversion (Standard)."""
        settings = Settings(
            database_url="postgresql://user:pass@host:5432/dbname",
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.async_database_url == "postgresql+asyncpg://user:pass@host:5432/dbname"

    @staticmethod
    def test_digitalocean_postgresql_url():
        """Test DigitalOcean PostgreSQL URL conversion."""
        do_url = "postgresql://user:pass@db-postgresql-sgp1-12345.ondigitalocean.com:25060/defaultdb"
        settings = Settings(
            database_url=do_url,
            _env_file=None,  # type: ignore[call-arg]
        )
        expected = "postgresql+asyncpg://user:pass@db-postgresql-sgp1-12345.ondigitalocean.com:25060/defaultdb"
        assert settings.async_database_url == expected

    @staticmethod
    def test_database_url_from_env(clear_settings_cache):
        """Test database URL from environment variable."""
        test_url = "postgresql://envuser:envpass@envhost:5432/envdb"
        with patch.dict(os.environ, {"DATABASE_URL": test_url}, clear=False):
            settings = Settings(_env_file=None)  # type: ignore[call-arg]
            assert settings.database_url == test_url

    @staticmethod
    def test_connection_pool_pre_ping():
        """Test that connection pool has pre_ping enabled."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            engine = create_async_engine(
                f"sqlite+aiosqlite:///{db_path}",
                pool_pre_ping=True,
            )
            # Check that pool_pre_ping option is set on the engine
            assert engine.pool._pre_ping is True
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

    @pytest_asyncio.fixture
    async def test_engine_local(self):
        """Create a local test engine for connection tests."""
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            echo=False,
        )
        yield engine
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_async_engine_connection(self, test_engine_local):
        """Test async engine can execute queries."""
        async with test_engine_local.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            row = result.fetchone()
            assert row[0] == 1


class TestMigration:
    """1.2 マイグレーションテスト"""

    @pytest.mark.asyncio
    async def test_create_all_tables(self, test_engine):
        """Test that all tables are created correctly."""
        # Import all models to register them
        from app import models  # noqa: F401

        async with test_engine.connect() as conn:
            # Check that tables exist by querying sqlite_master
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
            tables = [row[0] for row in result.fetchall()]

            # Should have upload_history table at minimum
            assert "upload_history" in tables

    @pytest.mark.asyncio
    async def test_model_persistence(self, test_session: AsyncSession):
        """Test data integrity when persisting models."""
        from datetime import UTC, datetime

        from app.models import UploadHistory

        # Create a record
        history = UploadHistory(
            drive_file_id="test-file-id",
            drive_file_name="test_video.mp4",
            drive_md5_checksum="abc123",
            youtube_video_id="yt-123",
            youtube_video_url="https://youtube.com/watch?v=yt-123",
            folder_path="/test/folder",
            status="completed",
            uploaded_at=datetime.now(UTC),
        )
        test_session.add(history)
        await test_session.commit()

        # Verify data integrity
        await test_session.refresh(history)
        assert history.id is not None
        assert history.drive_file_id == "test-file-id"
        assert history.drive_file_name == "test_video.mp4"
        assert history.drive_md5_checksum == "abc123"
        assert history.youtube_video_id == "yt-123"
        assert history.status == "completed"

    @pytest.mark.asyncio
    async def test_rollback_on_error(self, test_session: AsyncSession):
        """Test that rollback works correctly on error."""
        from datetime import UTC, datetime

        from app.models import UploadHistory

        # Start a transaction
        history = UploadHistory(
            drive_file_id="rollback-test",
            drive_file_name="rollback.mp4",
            drive_md5_checksum="xyz789",
            youtube_video_id="yt-rollback",
            youtube_video_url="https://youtube.com/watch?v=yt-rollback",
            status="completed",
            uploaded_at=datetime.now(UTC),
        )
        test_session.add(history)

        # Simulate error by rolling back
        await test_session.rollback()

        # Verify record was not persisted
        from sqlalchemy import select
        result = await test_session.execute(
            select(UploadHistory).where(UploadHistory.drive_file_id == "rollback-test")
        )
        assert result.scalars().first() is None

    @pytest.mark.asyncio
    async def test_multiple_records_persistence(self, test_session: AsyncSession):
        """Test multiple records can be persisted and retrieved."""
        from datetime import UTC, datetime

        from app.models import UploadHistory

        # Create multiple records
        for i in range(5):
            history = UploadHistory(
                drive_file_id=f"file-{i}",
                drive_file_name=f"video_{i}.mp4",
                drive_md5_checksum=f"md5-{i}",
                youtube_video_id=f"yt-{i}",
                youtube_video_url=f"https://youtube.com/watch?v=yt-{i}",
                status="completed",
                uploaded_at=datetime.now(UTC),
            )
            test_session.add(history)

        await test_session.commit()

        # Verify all records
        from sqlalchemy import func, select
        result = await test_session.execute(
            select(func.count()).select_from(UploadHistory)
        )
        count = result.scalar()
        assert count == 5

    @pytest.mark.asyncio
    async def test_unique_constraint_on_index(self, test_session: AsyncSession):
        """Test that indexed fields work correctly for queries."""
        from datetime import UTC, datetime

        from sqlalchemy import select

        from app.models import UploadHistory

        # Create records with same MD5 (index allows duplicates by design)
        for i in range(2):
            history = UploadHistory(
                drive_file_id=f"dup-file-{i}",
                drive_file_name=f"video_{i}.mp4",
                drive_md5_checksum="same-md5",
                youtube_video_id=f"yt-dup-{i}",
                youtube_video_url=f"https://youtube.com/watch?v=yt-dup-{i}",
                status="completed",
                uploaded_at=datetime.now(UTC),
            )
            test_session.add(history)

        await test_session.commit()

        # Query by MD5 should return both
        result = await test_session.execute(
            select(UploadHistory).where(UploadHistory.drive_md5_checksum == "same-md5")
        )
        records = result.scalars().all()
        assert len(records) == 2
