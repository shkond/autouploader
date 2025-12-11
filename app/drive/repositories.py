"""Google Drive API repository layer.

Provides low-level API access abstraction for Google Drive operations.
This layer handles direct API calls while the Service layer handles business logic.
"""

import io
from typing import Any

from anyio.to_thread import run_sync
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from app.core.protocols import DriveRepositoryProtocol
from app.drive.schemas import DriveFile, DriveFolder, FileType

# Video MIME types that can be uploaded to YouTube
VIDEO_MIME_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-ms-wmv",
    "video/x-flv",
    "video/webm",
    "video/3gpp",
    "video/mpeg",
    "video/x-matroska",
}


class DriveRepository(DriveRepositoryProtocol):
    """Repository for Google Drive API operations.

    Implements DriveRepositoryProtocol to provide a clean abstraction
    over the Google Drive API. All public methods are async.
    """

    def __init__(self, credentials: Credentials) -> None:
        """Initialize Drive repository with credentials.

        Args:
            credentials: Google OAuth credentials
        """
        self._credentials = credentials
        self._service = build("drive", "v3", credentials=credentials)

    @staticmethod
    async def _execute_async(request: Any, cancellable: bool = True) -> Any:
        """Execute a Google API request asynchronously.

        Wraps the blocking execute() call in run_sync to avoid blocking the event loop.

        Args:
            request: Google API request object with execute() method
            cancellable: Whether the operation can be cancelled (default: True)

        Returns:
            API response
        """
        return await run_sync(request.execute, cancellable=cancellable)

    async def list_files_raw(
        self,
        folder_id: str = "root",
        video_only: bool = True,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """List files in a folder (raw API response).

        Args:
            folder_id: Drive folder ID (default: root)
            video_only: Filter to show only video files
            page_size: Number of files per page

        Returns:
            List of raw file dicts from API
        """
        query = f"'{folder_id}' in parents and trashed = false"
        if video_only:
            mime_conditions = " or ".join(
                f"mimeType = '{mt}'" for mt in VIDEO_MIME_TYPES
            )
            folder_condition = "mimeType = 'application/vnd.google-apps.folder'"
            query += f" and ({mime_conditions} or {folder_condition})"

        fields = (
            "nextPageToken, files(id, name, mimeType, size, createdTime, "
            "modifiedTime, parents, thumbnailLink, webViewLink, md5Checksum)"
        )

        files: list[dict[str, Any]] = []
        page_token = None

        while True:
            request = self._service.files().list(
                q=query,
                pageSize=page_size,
                fields=fields,
                pageToken=page_token,
                orderBy="name",
            )
            response = await self._execute_async(request)

            files.extend(response.get("files", []))

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return files

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
        raw_files = await self.list_files_raw(folder_id, video_only, page_size)

        files: list[DriveFile] = []
        for item in raw_files:
            file_type = self._determine_file_type(item.get("mimeType", ""))
            parent_id = None
            if item.get("parents"):
                parent_id = item["parents"][0]

            files.append(
                DriveFile(
                    id=item["id"],
                    name=item["name"],
                    mimeType=item.get("mimeType", ""),
                    size=int(item["size"]) if item.get("size") else None,
                    createdTime=item.get("createdTime"),
                    modifiedTime=item.get("modifiedTime"),
                    file_type=file_type,
                    parent_id=parent_id,
                    thumbnailLink=item.get("thumbnailLink"),
                    webViewLink=item.get("webViewLink"),
                )
            )

        return files

    async def get_file_metadata(self, file_id: str) -> dict[str, Any]:
        """Get file metadata including MD5 checksum.

        Args:
            file_id: Drive file ID

        Returns:
            File metadata dict with md5Checksum
        """
        request = self._service.files().get(
            fileId=file_id,
            fields="id, name, mimeType, size, createdTime, modifiedTime, md5Checksum",
        )
        return await self._execute_async(request)

    async def get_folder_info(self, folder_id: str) -> dict[str, Any]:
        """Get folder metadata.

        Args:
            folder_id: Drive folder ID

        Returns:
            Folder metadata dict
        """
        request = self._service.files().get(
            fileId=folder_id, fields="id, name, mimeType"
        )
        return await self._execute_async(request)

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
        # Get folder info
        if folder_id == "root":
            folder_info = {"id": "root", "name": "My Drive"}
        else:
            folder_info = await self.get_folder_info(folder_id)

        # List files
        files = await self.list_files(folder_id, video_only)

        # Separate videos and folders
        video_files = [f for f in files if f.file_type == FileType.VIDEO]
        folder_files = [f for f in files if f.file_type == FileType.FOLDER]

        subfolders: list[DriveFolder] = []
        total_videos = len(video_files)

        if recursive:
            for subfolder_file in folder_files:
                subfolder = await self.scan_folder(
                    subfolder_file.id, recursive=True, video_only=video_only
                )
                subfolders.append(subfolder)
                total_videos += subfolder.total_videos

        return DriveFolder(
            id=folder_info["id"],
            name=folder_info["name"],
            files=video_files,
            subfolders=subfolders,
            total_videos=total_videos,
        )

    def get_file_content_stream(
        self, file_id: str
    ) -> tuple[io.BytesIO, MediaIoBaseDownload]:
        """Get a file content stream for downloading.

        Note: This method is synchronous as it only creates the downloader.
        The actual download (next_chunk calls) should be run in a thread pool.

        Args:
            file_id: Drive file ID

        Returns:
            Tuple of (BytesIO buffer, MediaIoBaseDownload instance)
        """
        request = self._service.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        return buffer, downloader

    def download_to_file(
        self, file_id: str, file_handle: io.IOBase
    ) -> MediaIoBaseDownload:
        """Download a file to a file handle (e.g., temp file).

        This is more memory-efficient than get_file_content_stream for large files
        as it writes directly to disk instead of holding the entire file in memory.

        Note: This method is synchronous as it only creates the downloader.
        The actual download (next_chunk calls) should be run in a thread pool.

        Args:
            file_id: Drive file ID
            file_handle: Writable file handle (e.g., open temp file in 'wb' mode)

        Returns:
            MediaIoBaseDownload instance for chunked downloading
        """
        request = self._service.files().get_media(fileId=file_id)
        downloader = MediaIoBaseDownload(file_handle, request)
        return downloader

    @staticmethod
    def _determine_file_type(mime_type: str) -> FileType:
        """Determine file type from MIME type.

        Args:
            mime_type: MIME type string

        Returns:
            FileType enum value
        """
        if mime_type == "application/vnd.google-apps.folder":
            return FileType.FOLDER
        if mime_type in VIDEO_MIME_TYPES:
            return FileType.VIDEO
        return FileType.OTHER
