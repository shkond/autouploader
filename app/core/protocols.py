"""Protocol definitions for repository layer interfaces.

These protocols define the contracts for data access layers, enabling
dependency injection and easier testing through mock implementations.
"""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import io
    from uuid import UUID

    from google.oauth2.credentials import Credentials

    from app.drive.schemas import DriveFile, DriveFolder
    from app.queue.schemas import JobStatus, QueueJob, QueueJobCreate, QueueStatus
    from app.youtube.schemas import UploadResult, VideoMetadata


class DriveRepositoryProtocol(Protocol):
    """Protocol for Google Drive API operations.

    Defines the contract for Drive data access, abstracting
    the underlying Google API calls.
    """

    async def list_files(
        self,
        folder_id: str = "root",
        video_only: bool = True,
        page_size: int = 100,
    ) -> list["DriveFile"]:
        """List files in a folder.

        Args:
            folder_id: Drive folder ID (default: root)
            video_only: Filter to show only video files
            page_size: Number of files per page

        Returns:
            List of DriveFile objects
        """
        ...

    async def get_file_metadata(self, file_id: str) -> dict:
        """Get file metadata including MD5 checksum.

        Args:
            file_id: Drive file ID

        Returns:
            File metadata dict with md5Checksum
        """
        ...

    async def get_folder_info(self, folder_id: str) -> dict:
        """Get folder metadata.

        Args:
            folder_id: Drive folder ID

        Returns:
            Folder metadata dict
        """
        ...

    async def scan_folder(
        self,
        folder_id: str = "root",
        recursive: bool = False,
        video_only: bool = True,
    ) -> "DriveFolder":
        """Scan a folder and return its contents.

        Args:
            folder_id: Drive folder ID
            recursive: Whether to scan subfolders
            video_only: Filter to show only video files

        Returns:
            DriveFolder with files and subfolders
        """
        ...

    def get_file_content_stream(
        self, file_id: str
    ) -> tuple["io.BytesIO", object]:
        """Get a file content stream for downloading.

        Args:
            file_id: Drive file ID

        Returns:
            Tuple of (BytesIO buffer, MediaIoBaseDownload instance)
        """
        ...


class YouTubeRepositoryProtocol(Protocol):
    """Protocol for YouTube Data API operations.

    Defines the contract for YouTube data access, abstracting
    the underlying Google API calls.
    """

    async def upload_video(
        self,
        file_stream: "io.BytesIO",
        metadata: "VideoMetadata",
        file_size: int,
        mime_type: str = "video/mp4",
    ) -> "UploadResult":
        """Upload a video to YouTube.

        Args:
            file_stream: BytesIO stream containing video data
            metadata: Video metadata
            file_size: Size of the video file in bytes
            mime_type: Video MIME type

        Returns:
            UploadResult with video ID and URL
        """
        ...

    async def get_channel_info(self) -> dict:
        """Get authenticated user's YouTube channel information.

        Returns:
            Channel information dict
        """
        ...

    async def list_videos(self, max_results: int = 25) -> list[dict]:
        """List videos uploaded by the authenticated user.

        Args:
            max_results: Maximum number of videos to return

        Returns:
            List of video information dicts
        """
        ...

    async def check_video_exists(self, video_id: str) -> bool:
        """Check if a video exists on YouTube.

        Args:
            video_id: YouTube video ID to check

        Returns:
            True if video exists, False otherwise
        """
        ...


class QueueRepositoryProtocol(Protocol):
    """Protocol for queue database operations.

    Defines the contract for queue data access, abstracting
    the underlying database operations.
    """

    async def add_job(
        self,
        job_create: "QueueJobCreate",
        user_id: str,
    ) -> "QueueJob":
        """Add a new job to the queue.

        Args:
            job_create: Job creation request
            user_id: User ID who created this job

        Returns:
            Created QueueJob
        """
        ...

    async def get_job(self, job_id: "UUID") -> "QueueJob | None":
        """Get a job by ID.

        Args:
            job_id: Job UUID

        Returns:
            QueueJob or None if not found
        """
        ...

    async def update_job(
        self,
        job_id: "UUID",
        status: "JobStatus | None" = None,
        progress: float | None = None,
        message: str | None = None,
        video_id: str | None = None,
        video_url: str | None = None,
        error: str | None = None,
    ) -> "QueueJob | None":
        """Update a job's status and progress.

        Args:
            job_id: Job UUID
            status: New status (optional)
            progress: New progress (optional)
            message: Status message (optional)
            video_id: YouTube video ID (optional)
            video_url: YouTube video URL (optional)
            error: Error message (optional)

        Returns:
            Updated QueueJob or None if not found
        """
        ...

    async def get_pending_jobs(self) -> list["QueueJob"]:
        """Get all pending jobs.

        Returns:
            List of pending QueueJobs
        """
        ...

    async def get_next_pending_job(self) -> "QueueJob | None":
        """Get the next pending job in queue order (FIFO).

        Returns:
            Next pending QueueJob or None
        """
        ...

    async def get_jobs_by_user(self, user_id: str) -> list["QueueJob"]:
        """Get all jobs for a specific user.

        Args:
            user_id: User identifier

        Returns:
            List of QueueJobs belonging to the user
        """
        ...

    async def get_status(self, user_id: str | None = None) -> "QueueStatus":
        """Get overall queue status, optionally filtered by user.

        Args:
            user_id: Optional user ID to filter by

        Returns:
            QueueStatus summary
        """
        ...

    async def is_file_id_in_queue(self, drive_file_id: str) -> bool:
        """Check if a file ID is already in the queue.

        Args:
            drive_file_id: Google Drive file ID

        Returns:
            True if file is already in queue
        """
        ...

    async def is_md5_in_queue(self, md5_checksum: str) -> bool:
        """Check if a file with given MD5 is already in the queue.

        Args:
            md5_checksum: MD5 checksum of the file

        Returns:
            True if file with same MD5 is in queue
        """
        ...


class AuthRepositoryProtocol(Protocol):
    """Protocol for authentication data operations.

    Defines the contract for auth data access, abstracting
    token storage and session management.
    """

    async def get_credentials(self, user_id: str) -> "Credentials | None":
        """Get OAuth credentials for a user.

        Args:
            user_id: User identifier

        Returns:
            Credentials or None if not found
        """
        ...

    async def save_credentials(
        self,
        user_id: str,
        credentials: "Credentials",
    ) -> None:
        """Save OAuth credentials for a user.

        Args:
            user_id: User identifier
            credentials: Google OAuth credentials
        """
        ...

    async def delete_credentials(self, user_id: str) -> bool:
        """Delete OAuth credentials for a user.

        Args:
            user_id: User identifier

        Returns:
            True if deleted, False if not found
        """
        ...
