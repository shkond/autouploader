"""Google Drive service layer for business logic.

Provides high-level operations for Google Drive, using the Repository layer
for API access and implementing business logic like filtering and validation.
"""

from typing import Any

from google.oauth2.credentials import Credentials

from app.core.protocols import DriveRepositoryProtocol
from app.drive.repositories import DriveRepository
from app.drive.schemas import DriveFile, DriveFolder, FileType


class DriveService:
    """Service for Google Drive business logic.

    Uses DriveRepository for API access and implements business logic
    like video filtering, size validation, and metadata processing.
    """

    def __init__(
        self,
        repository: DriveRepositoryProtocol | None = None,
        credentials: Credentials | None = None,
    ) -> None:
        """Initialize Drive service.

        Args:
            repository: Optional repository for testing/DI. If not provided,
                        credentials must be provided to create a default repository.
            credentials: Google OAuth credentials (used if repository not provided)

        Raises:
            ValueError: If neither repository nor credentials are provided
        """
        if repository is not None:
            self._repository = repository
        elif credentials is not None:
            self._repository = DriveRepository(credentials)
        else:
            raise ValueError("Either repository or credentials must be provided")

        # Store credentials for compatibility with legacy code
        self._credentials = credentials

    @property
    def repository(self) -> DriveRepositoryProtocol:
        """Get the underlying repository."""
        return self._repository

    async def list_files(
        self,
        folder_id: str = "root",
        video_only: bool = True,
        page_size: int = 100,
    ) -> list[DriveFile]:
        """List files in a folder.

        Args:
            folder_id: Drive folder ID (default: root)
            video_only: Filter to show only video files
            page_size: Number of files per page

        Returns:
            List of DriveFile objects
        """
        return await self._repository.list_files(folder_id, video_only, page_size)

    async def get_folder_info(self, folder_id: str) -> dict[str, Any]:
        """Get folder metadata.

        Args:
            folder_id: Drive folder ID

        Returns:
            Folder metadata dict
        """
        return await self._repository.get_folder_info(folder_id)

    async def scan_folder(
        self,
        folder_id: str = "root",
        recursive: bool = False,
        video_only: bool = True,
    ) -> DriveFolder:
        """Scan a folder and return its contents.

        Args:
            folder_id: Drive folder ID
            recursive: Whether to scan subfolders
            video_only: Filter to show only video files

        Returns:
            DriveFolder with files and subfolders
        """
        return await self._repository.scan_folder(folder_id, recursive, video_only)

    def get_file_content_stream(self, file_id: str):
        """Get a file content stream for downloading.

        Note: This method is synchronous as it only creates the downloader.

        Args:
            file_id: Drive file ID

        Returns:
            Tuple of (BytesIO buffer, MediaIoBaseDownload instance)
        """
        return self._repository.get_file_content_stream(file_id)

    def download_to_file(self, file_id: str, file_handle):
        """Download a file to a file handle.

        Args:
            file_id: Drive file ID
            file_handle: Writable file handle

        Returns:
            MediaIoBaseDownload instance
        """
        return self._repository.download_to_file(file_id, file_handle)

    async def get_file_metadata(self, file_id: str) -> dict[str, Any]:
        """Get file metadata including MD5 checksum.

        Args:
            file_id: Drive file ID

        Returns:
            File metadata dict with md5Checksum
        """
        return await self._repository.get_file_metadata(file_id)

    async def get_all_videos_flat(
        self,
        folder_id: str,
        recursive: bool = False,
        max_files: int = 100,
        folder_path: str = "",
    ) -> list[tuple[dict[str, Any], str]]:
        """Get all video files from a folder as a flat list.

        Args:
            folder_id: Drive folder ID
            recursive: Whether to scan subfolders
            max_files: Maximum number of files to return
            folder_path: Current folder path (for tracking)

        Returns:
            List of tuples (file_metadata, folder_path)
        """
        result: list[tuple[dict[str, Any], str]] = []

        # Get folder info for path
        if folder_id == "root":
            current_path = folder_path or "My Drive"
        else:
            folder_info = await self.get_folder_info(folder_id)
            current_path = (
                f"{folder_path}/{folder_info['name']}"
                if folder_path
                else folder_info["name"]
            )

        # List files in folder
        files = await self.list_files(folder_id, video_only=True)

        for file in files:
            if len(result) >= max_files:
                break

            if file.file_type == FileType.VIDEO:
                # Get full metadata including MD5
                file_meta = await self.get_file_metadata(file.id)
                file_meta["folder_path"] = current_path
                result.append((file_meta, current_path))

            elif file.file_type == FileType.FOLDER and recursive:
                if len(result) < max_files:
                    sub_files = await self.get_all_videos_flat(
                        file.id,
                        recursive=True,
                        max_files=max_files - len(result),
                        folder_path=current_path,
                    )
                    result.extend(sub_files)

        return result[:max_files]

    @staticmethod
    def get_uploadable_files(
        files: list[DriveFile]
    ) -> list[DriveFile]:
        """Filter files to get only uploadable video files.

        Args:
            files: List of DriveFile objects

        Returns:
            Filtered list of video files that can be uploaded
        """
        return [f for f in files if f.file_type == FileType.VIDEO]

    @staticmethod
    def is_video_file(mime_type: str) -> bool:
        """Check if a MIME type is a supported video type.

        Args:
            mime_type: MIME type string

        Returns:
            True if video file, False otherwise
        """
        from app.drive.repositories import VIDEO_MIME_TYPES

        return mime_type in VIDEO_MIME_TYPES
