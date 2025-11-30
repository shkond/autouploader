"""YouTube service for video uploads."""

import io
import logging
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload

from app.auth.oauth import get_oauth_service
from app.config import get_settings
from app.drive.service import get_drive_service
from app.youtube.schemas import (
    UploadProgress,
    UploadResult,
    VideoMetadata,
)

logger = logging.getLogger(__name__)


class YouTubeService:
    """Service for interacting with YouTube Data API."""

    YOUTUBE_API_SERVICE_NAME = "youtube"
    YOUTUBE_API_VERSION = "v3"

    def __init__(self, credentials: Credentials) -> None:
        """Initialize YouTube service with credentials.

        Args:
            credentials: Google OAuth credentials
        """
        self.service = build(
            self.YOUTUBE_API_SERVICE_NAME,
            self.YOUTUBE_API_VERSION,
            credentials=credentials,
        )
        self.settings = get_settings()

    def upload_video(
        self,
        file_stream: io.BytesIO,
        metadata: VideoMetadata,
        file_size: int,
        mime_type: str = "video/mp4",
        progress_callback: Any | None = None,
        file_id: str = "",
    ) -> UploadResult:
        """Upload a video to YouTube using resumable upload.

        Args:
            file_stream: BytesIO stream containing video data
            metadata: Video metadata
            file_size: Size of the video file in bytes
            mime_type: Video MIME type
            progress_callback: Optional callback for progress updates
            file_id: Optional file ID for progress tracking

        Returns:
            UploadResult with video ID and URL
        """
        body = {
            "snippet": {
                "title": metadata.title,
                "description": metadata.description,
                "tags": metadata.tags,
                "categoryId": metadata.category_id,
            },
            "status": {
                "privacyStatus": metadata.privacy_status.value,
                "selfDeclaredMadeForKids": metadata.made_for_kids,
            },
        }

        media = MediaIoBaseUpload(
            file_stream,
            mimetype=mime_type,
            chunksize=self.settings.upload_chunk_size,
            resumable=True,
        )

        try:
            request = self.service.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
                notifySubscribers=metadata.notify_subscribers,
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status and progress_callback:
                    progress = status.progress() * 100
                    progress_callback(
                        UploadProgress(
                            file_id=file_id,
                            status="uploading",
                            progress=progress,
                            bytes_uploaded=int(status.resumable_progress),
                            total_bytes=file_size,
                            message=f"Uploading: {progress:.1f}%",
                        )
                    )

            video_id = response.get("id")
            return UploadResult(
                success=True,
                video_id=video_id,
                video_url=f"https://www.youtube.com/watch?v={video_id}",
                message="Upload completed successfully",
            )

        except HttpError as e:
            logger.exception("YouTube upload failed")
            return UploadResult(
                success=False,
                message="Upload failed",
                error=str(e),
            )

    def upload_from_drive(
        self,
        drive_file_id: str,
        metadata: VideoMetadata,
        progress_callback: Any | None = None,
    ) -> UploadResult:
        """Upload a video from Google Drive to YouTube.

        This method downloads the video from Drive and uploads it to YouTube
        using resumable upload for reliability.

        Args:
            drive_file_id: Google Drive file ID
            metadata: Video metadata for YouTube
            progress_callback: Optional callback for progress updates

        Returns:
            UploadResult with video ID and URL
        """
        try:
            # Get Drive service
            drive_service = get_drive_service()

            # Get file metadata
            file_info = drive_service.get_file_metadata(drive_file_id)
            file_size = int(file_info.get("size", 0))
            mime_type = file_info.get("mimeType", "video/mp4")

            if progress_callback:
                progress_callback(
                    UploadProgress(
                        file_id=drive_file_id,
                        status="downloading",
                        progress=0,
                        total_bytes=file_size,
                        message="Starting download from Drive...",
                    )
                )

            # Download file from Drive
            buffer, downloader = drive_service.get_file_content_stream(drive_file_id)

            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status and progress_callback:
                    progress = status.progress() * 50  # 0-50% for download
                    progress_callback(
                        UploadProgress(
                            file_id=drive_file_id,
                            status="downloading",
                            progress=progress,
                            bytes_uploaded=int(status.resumable_progress),
                            total_bytes=file_size,
                            message=f"Downloading from Drive: {progress:.1f}%",
                        )
                    )

            # Reset buffer position for upload
            buffer.seek(0)

            if progress_callback:
                progress_callback(
                    UploadProgress(
                        file_id=drive_file_id,
                        status="uploading",
                        progress=50,
                        total_bytes=file_size,
                        message="Starting YouTube upload...",
                    )
                )

            # Upload to YouTube
            def adjusted_progress_callback(progress: UploadProgress) -> None:
                if progress_callback:
                    # Adjust progress to 50-100% for upload phase
                    adjusted = UploadProgress(
                        file_id=drive_file_id,
                        status=progress.status,
                        progress=50 + (progress.progress / 2),
                        bytes_uploaded=progress.bytes_uploaded,
                        total_bytes=progress.total_bytes,
                        message=progress.message,
                    )
                    progress_callback(adjusted)

            result = self.upload_video(
                buffer,
                metadata,
                file_size,
                mime_type,
                adjusted_progress_callback if progress_callback else None,
                file_id=drive_file_id,
            )

            return result

        except ValueError as e:
            return UploadResult(
                success=False,
                message="Authentication error",
                error=str(e),
            )
        except Exception as e:
            logger.exception("Upload from Drive failed")
            return UploadResult(
                success=False,
                message="Upload failed",
                error=str(e),
            )

    def get_channel_info(self) -> dict[str, Any]:
        """Get authenticated user's YouTube channel information.

        Returns:
            Channel information dict
        """
        response = (
            self.service.channels().list(part="snippet,statistics", mine=True).execute()
        )
        items = response.get("items", [])
        if items:
            return items[0]
        return {}

    def list_my_videos(self, max_results: int = 25) -> list[dict[str, Any]]:
        """List videos uploaded by the authenticated user.

        Args:
            max_results: Maximum number of videos to return

        Returns:
            List of video information dicts
        """
        response = (
            self.service.search()
            .list(
                part="snippet",
                forMine=True,
                type="video",
                maxResults=max_results,
            )
            .execute()
        )
        return response.get("items", [])


def get_youtube_service() -> YouTubeService:
    """Get YouTube service with current credentials.

    Returns:
        YouTubeService instance

    Raises:
        ValueError: If not authenticated
    """
    oauth_service = get_oauth_service()
    credentials = oauth_service.get_credentials()
    if not credentials:
        raise ValueError("Not authenticated. Please login first.")
    return YouTubeService(credentials)
