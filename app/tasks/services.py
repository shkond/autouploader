"""Folder scanning and queue management service.

Shared logic between Web API (upload_folder) and CLI (scheduled_upload).
"""

import uuid
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.drive.schemas import FolderUploadSettings, SkippedFile
from app.models import UploadHistory
from app.queue.repositories import QueueRepository
from app.queue.schemas import QueueJob, QueueJobCreate
from app.youtube.schemas import PrivacyStatus, VideoMetadata

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.drive.services import DriveService


@dataclass
class FolderProcessResult:
    """Result of folder processing."""

    folder_name: str
    batch_id: str
    added_jobs: list[QueueJob]
    skipped_files: list[SkippedFile]


class FolderUploadService:
    """Service for folder scanning and queue management.

    Provides unified logic for scanning Drive folders and adding videos
    to the upload queue with duplicate detection.
    """

    def __init__(
        self,
        drive_service: "DriveService",
        db: "AsyncSession",
    ) -> None:
        """Initialize FolderUploadService.

        Args:
            drive_service: DriveService instance with user credentials
            db: Database session for queue operations
        """
        self._drive = drive_service
        self._db = db
        self._repo = QueueRepository(db)

    async def process_folder(
        self,
        folder_id: str,
        user_id: str,
        settings: FolderUploadSettings,
        recursive: bool = True,
        max_files: int = 50,
        skip_duplicates: bool = True,
    ) -> FolderProcessResult:
        """Scan folder and add videos to queue with duplicate detection.

        Args:
            folder_id: Google Drive folder ID
            user_id: User ID for the queue jobs
            settings: Upload settings (title template, privacy, etc.)
            recursive: Whether to scan subfolders
            max_files: Maximum number of files to process
            skip_duplicates: Whether to skip duplicate files

        Returns:
            FolderProcessResult with added jobs and skipped files
        """
        # Get folder info
        if folder_id == "root":
            folder_name = "My Drive"
        else:
            folder_info = await self._drive.get_folder_info(folder_id)
            folder_name = folder_info["name"]

        batch_id = str(uuid.uuid4())

        # Scan folder for videos
        video_files = await self._drive.get_all_videos_flat(
            folder_id=folder_id,
            recursive=recursive,
            max_files=max_files,
        )

        added_jobs: list[QueueJob] = []
        skipped_files: list[SkippedFile] = []

        for file_meta, folder_path in video_files:
            file_id = file_meta["id"]
            file_name = file_meta["name"]
            md5_checksum = file_meta.get("md5Checksum", "")

            # Check for duplicates
            if skip_duplicates:
                skip_reason = await self._check_duplicates(file_id, md5_checksum)
                if skip_reason:
                    skipped_files.append(
                        SkippedFile(
                            file_id=file_id,
                            file_name=file_name,
                            reason=skip_reason,
                        )
                    )
                    continue

            # Generate video metadata from template
            video_metadata = self._create_video_metadata(
                file_name, folder_name, folder_path, md5_checksum, settings
            )

            # Create queue job
            job_create = QueueJobCreate(
                drive_file_id=file_id,
                drive_file_name=file_name,
                drive_md5_checksum=md5_checksum,
                folder_path=folder_path,
                batch_id=batch_id,
                metadata=video_metadata,
            )

            job = await self._repo.add_job(job_create, user_id)
            added_jobs.append(job)

        return FolderProcessResult(
            folder_name=folder_name,
            batch_id=batch_id,
            added_jobs=added_jobs,
            skipped_files=skipped_files,
        )

    async def _check_duplicates(
        self, file_id: str, md5_checksum: str
    ) -> str | None:
        """Check for duplicates in queue AND upload history.

        Args:
            file_id: Google Drive file ID
            md5_checksum: MD5 checksum of the file

        Returns:
            Reason string if duplicate found, None otherwise
        """
        # Check if already in queue (by file ID)
        if await self._repo.is_file_id_in_queue(file_id):
            return "already_in_queue"

        # Check if already in queue (by MD5)
        if md5_checksum and await self._repo.is_md5_in_queue(md5_checksum):
            return "duplicate_md5_in_queue"

        # Check if already uploaded (in UploadHistory)
        if md5_checksum:
            result = await self._db.execute(
                select(UploadHistory).where(
                    UploadHistory.drive_md5_checksum == md5_checksum
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                return f"already_uploaded:{existing.youtube_video_id}"

        return None

    @staticmethod
    def _create_video_metadata(
        file_name: str,
        folder_name: str,
        folder_path: str,
        md5_checksum: str,
        settings: FolderUploadSettings,
    ) -> VideoMetadata:
        """Create video metadata from template.

        Args:
            file_name: Original file name
            folder_name: Parent folder name
            folder_path: Full folder path
            md5_checksum: File MD5 checksum
            settings: Upload settings with templates

        Returns:
            VideoMetadata for YouTube upload
        """
        today = date.today().isoformat()
        title_base = file_name.rsplit(".", 1)[0] if "." in file_name else file_name

        # Process templates
        title = settings.title_template.format(
            filename=title_base,
            folder=folder_name,
            folder_path=folder_path,
            upload_date=today,
        )
        description = settings.description_template.format(
            filename=title_base,
            folder=folder_name,
            folder_path=folder_path,
            upload_date=today,
        )

        # Add MD5 hash to description if enabled
        if settings.include_md5_hash and md5_checksum:
            description += f"\n\n[MD5:{md5_checksum}]"

        # Map privacy status
        privacy_map = {
            "public": PrivacyStatus.PUBLIC,
            "private": PrivacyStatus.PRIVATE,
            "unlisted": PrivacyStatus.UNLISTED,
        }

        return VideoMetadata(
            title=title[:100],  # YouTube title limit
            description=description[:5000],  # YouTube description limit
            tags=settings.default_tags,
            category_id=settings.default_category_id,
            privacy_status=privacy_map.get(settings.default_privacy, PrivacyStatus.PRIVATE),
            made_for_kids=settings.made_for_kids,
        )
