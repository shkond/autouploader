"""Tests for FolderUploadService (app/tasks/services.py).

Test categories:
- _create_video_metadata: template processing, placeholder handling
- _check_duplicates: queue and history duplicate detection
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.drive.schemas import FolderUploadSettings
from app.tasks.services import FolderUploadService
from app.youtube.schemas import PrivacyStatus


class TestCreateVideoMetadata:
    """Tests for _create_video_metadata static method."""

    def test_basic_metadata_generation(self) -> None:
        """Test basic metadata generation with valid templates."""
        settings = FolderUploadSettings(
            title_template="{filename}",
            description_template="From {folder_path}",
            default_privacy="private",
            include_md5_hash=False,
        )

        result = FolderUploadService._create_video_metadata(
            file_name="video.mp4",
            folder_name="My Folder",
            folder_path="Videos/My Folder",
            md5_checksum="abc123",
            settings=settings,
        )

        assert result.title == "video"
        assert result.description == "From Videos/My Folder"
        assert result.privacy_status == PrivacyStatus.PRIVATE

    def test_metadata_with_all_placeholders(self) -> None:
        """Test metadata with all supported placeholders."""
        settings = FolderUploadSettings(
            title_template="{filename} - {folder} - {upload_date}",
            description_template="File: {filename}\nFolder: {folder}\nPath: {folder_path}\nDate: {upload_date}",
            default_privacy="public",
            include_md5_hash=True,
        )

        result = FolderUploadService._create_video_metadata(
            file_name="test.mp4",
            folder_name="Uploads",
            folder_path="Root/Uploads",
            md5_checksum="def456",
            settings=settings,
        )

        today = date.today().isoformat()
        assert "test" in result.title
        assert "Uploads" in result.title
        assert today in result.title
        assert "[MD5:def456]" in result.description
        assert result.privacy_status == PrivacyStatus.PUBLIC

    def test_invalid_placeholder_fallback_title(self) -> None:
        """Test that invalid placeholder in title falls back to filename."""
        settings = FolderUploadSettings(
            title_template="{invalid_placeholder}",
            description_template="Description",
            default_privacy="private",
        )

        result = FolderUploadService._create_video_metadata(
            file_name="video.mp4",
            folder_name="Folder",
            folder_path="Path",
            md5_checksum="",
            settings=settings,
        )

        # Should fall back to title_base (filename without extension)
        assert result.title == "video"

    def test_invalid_placeholder_fallback_description(self) -> None:
        """Test that invalid placeholder in description falls back to default."""
        settings = FolderUploadSettings(
            title_template="{filename}",
            description_template="{unknown_field}",
            default_privacy="private",
        )

        result = FolderUploadService._create_video_metadata(
            file_name="video.mp4",
            folder_name="Folder",
            folder_path="Videos/Folder",
            md5_checksum="",
            settings=settings,
        )

        # Should fall back to default description
        assert result.description == "Uploaded from Videos/Folder"

    def test_title_truncation(self) -> None:
        """Test that title is truncated to 100 characters."""
        long_filename = "a" * 150
        settings = FolderUploadSettings(
            title_template="{filename}",
            description_template="Desc",
        )

        result = FolderUploadService._create_video_metadata(
            file_name=f"{long_filename}.mp4",
            folder_name="Folder",
            folder_path="Path",
            md5_checksum="",
            settings=settings,
        )

        assert len(result.title) <= 100

    def test_privacy_status_mapping(self) -> None:
        """Test privacy status mapping for all values."""
        for privacy, expected in [
            ("public", PrivacyStatus.PUBLIC),
            ("private", PrivacyStatus.PRIVATE),
            ("unlisted", PrivacyStatus.UNLISTED),
        ]:
            settings = FolderUploadSettings(
                title_template="{filename}",
                description_template="Desc",
                default_privacy=privacy,
            )

            result = FolderUploadService._create_video_metadata(
                file_name="video.mp4",
                folder_name="Folder",
                folder_path="Path",
                md5_checksum="",
                settings=settings,
            )

            assert result.privacy_status == expected


class TestCheckDuplicates:
    """Tests for _check_duplicates method."""

    @pytest.mark.asyncio
    async def test_no_duplicates(self) -> None:
        """Test that no duplicate returns None."""
        mock_db = AsyncMock()
        mock_drive = MagicMock()

        # Setup mock repo
        with patch("app.tasks.services.QueueRepository") as mock_repo_class:
            mock_repo = mock_repo_class.return_value
            mock_repo.is_file_id_in_queue = AsyncMock(return_value=False)
            mock_repo.is_md5_in_queue = AsyncMock(return_value=False)

            # Mock DB query for UploadHistory
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)

            service = FolderUploadService(mock_drive, mock_db)
            result = await service._check_duplicates("file123", "md5abc")

            assert result is None

    @pytest.mark.asyncio
    async def test_file_id_already_in_queue(self) -> None:
        """Test that file ID in queue returns 'already_in_queue'."""
        mock_db = AsyncMock()
        mock_drive = MagicMock()

        with patch("app.tasks.services.QueueRepository") as mock_repo_class:
            mock_repo = mock_repo_class.return_value
            mock_repo.is_file_id_in_queue = AsyncMock(return_value=True)

            service = FolderUploadService(mock_drive, mock_db)
            result = await service._check_duplicates("file123", "md5abc")

            assert result == "already_in_queue"

    @pytest.mark.asyncio
    async def test_md5_already_in_queue(self) -> None:
        """Test that MD5 in queue returns 'duplicate_md5_in_queue'."""
        mock_db = AsyncMock()
        mock_drive = MagicMock()

        with patch("app.tasks.services.QueueRepository") as mock_repo_class:
            mock_repo = mock_repo_class.return_value
            mock_repo.is_file_id_in_queue = AsyncMock(return_value=False)
            mock_repo.is_md5_in_queue = AsyncMock(return_value=True)

            service = FolderUploadService(mock_drive, mock_db)
            result = await service._check_duplicates("file123", "md5abc")

            assert result == "duplicate_md5_in_queue"

    @pytest.mark.asyncio
    async def test_already_uploaded_in_history(self) -> None:
        """Test that MD5 in upload history returns correct reason."""
        mock_db = AsyncMock()
        mock_drive = MagicMock()

        with patch("app.tasks.services.QueueRepository") as mock_repo_class:
            mock_repo = mock_repo_class.return_value
            mock_repo.is_file_id_in_queue = AsyncMock(return_value=False)
            mock_repo.is_md5_in_queue = AsyncMock(return_value=False)

            # Mock existing upload history
            mock_history = MagicMock()
            mock_history.youtube_video_id = "yt_video_123"
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_history
            mock_db.execute = AsyncMock(return_value=mock_result)

            service = FolderUploadService(mock_drive, mock_db)
            result = await service._check_duplicates("file123", "md5abc")

            assert result == "already_uploaded:yt_video_123"
