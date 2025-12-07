"""YouTube service for video uploads."""

import io
import json
import logging
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.auth.oauth import get_oauth_service
from app.config import get_settings
from app.drive.service import get_drive_service
from app.youtube.quota import get_quota_tracker
from app.youtube.schemas import (
    UploadProgress,
    UploadResult,
    VideoMetadata,
)

logger = logging.getLogger(__name__)


def _is_retryable_error(exception: BaseException) -> bool:
    """Check if an error is retryable (quota/rate limit).
    
    Args:
        exception: The exception to check
        
    Returns:
        True if the error should trigger a retry
    """
    if isinstance(exception, HttpError):
        # 403 = quota exceeded, 429 = rate limit
        if exception.resp.status in [403, 429]:
            error_reason = ""
            try:
                error_content = json.loads(exception.content.decode("utf-8"))
                error_reason = (
                    error_content.get("error", {})
                    .get("errors", [{}])[0]
                    .get("reason", "")
                )
            except (json.JSONDecodeError, KeyError, IndexError, UnicodeDecodeError) as e:
                logger.warning("Could not parse HttpError content for retry check: %s", e)

            # Retry on quota/rate limit errors, but not on permission errors
            if error_reason in ["quotaExceeded", "rateLimitExceeded", "userRateLimitExceeded"]:
                logger.warning(
                    "Retryable API error: status=%s, reason=%s",
                    exception.resp.status,
                    error_reason,
                )
                return True

            # 429 is always rate limit
            if exception.resp.status == 429:
                return True

    return False


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
        self._uploads_playlist_cache: str | None = None  # Cache for uploads playlist ID

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
        quota_tracker = get_quota_tracker()
        try:
            response = (
                self.service.channels().list(part="snippet,statistics", mine=True).execute()
            )
            items = response.get("items", [])
            if items:
                return items[0]
            return {}
        finally:
            # Track quota even if request fails
            quota_tracker.track("channels.list")

    def list_my_videos(self, max_results: int = 25) -> list[dict[str, Any]]:
        """List videos uploaded by the authenticated user.

        Note: This uses search.list which costs 100 quota units.
        For a more efficient alternative, use list_my_videos_optimized().

        Args:
            max_results: Maximum number of videos to return

        Returns:
            List of video information dicts
        """
        quota_tracker = get_quota_tracker()
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
        quota_tracker.track("search.list")
        return response.get("items", [])

    def check_video_exists_on_youtube(self, video_id: str) -> bool:
        """Check if a video exists on YouTube.
        
        This is useful for verifying that previously uploaded videos still exist.
        Costs only 1 quota unit.
        
        Args:
            video_id: YouTube video ID to check
            
        Returns:
            True if video exists, False otherwise
        """
        quota_tracker = get_quota_tracker()
        try:
            response = (
                self.service.videos()
                .list(
                    part="id",  # Minimal fields to reduce data transfer
                    id=video_id,
                )
                .execute()
            )
            return len(response.get("items", [])) > 0
        except HttpError as e:
            logger.warning("Failed to check video %s: %s", video_id, e)
            return False
        finally:
            # Track quota even if request fails
            quota_tracker.track("videos.list")

    def _get_uploads_playlist_id(self) -> str | None:
        """Get the uploads playlist ID for the authenticated channel.
        
        This is cached to avoid repeated API calls.
        Costs 1 quota unit on first call.
        
        Returns:
            Uploads playlist ID or None if not found
        """
        # Return cached value if available
        if self._uploads_playlist_cache is not None:
            return self._uploads_playlist_cache

        quota_tracker = get_quota_tracker()
        try:
            response = (
                self.service.channels()
                .list(
                    part="contentDetails",
                    mine=True,
                )
                .execute()
            )

            items = response.get("items", [])
            if not items:
                return None

            playlist_id = (
                items[0]
                .get("contentDetails", {})
                .get("relatedPlaylists", {})
                .get("uploads")
            )
            self._uploads_playlist_cache = playlist_id  # Cache the result
            return playlist_id
        except HttpError as e:
            logger.warning("Failed to get uploads playlist: %s", e)
            return None
        finally:
            # Track quota even if request fails
            quota_tracker.track("channels.list")

    def list_my_videos_optimized(
        self, max_results: int = 25
    ) -> list[dict[str, Any]]:
        """List videos using playlistItems API (optimized version).
        
        This uses playlistItems.list which costs only 1-2 quota units
        instead of search.list which costs 100 units.
        
        Args:
            max_results: Maximum number of videos to return
            
        Returns:
            List of video information dicts
        """
        quota_tracker = get_quota_tracker()

        # Get uploads playlist ID
        playlist_id = self._get_uploads_playlist_id()
        if not playlist_id:
            logger.warning("Could not get uploads playlist, falling back to search")
            return self.list_my_videos(max_results)

        try:
            response = (
                self.service.playlistItems()
                .list(
                    part="snippet,contentDetails",
                    playlistId=playlist_id,
                    maxResults=max_results,
                )
                .execute()
            )
            return response.get("items", [])
        except HttpError as e:
            logger.warning("Failed to list playlist items: %s", e)
            return []
        finally:
            # Track quota even if request fails
            quota_tracker.track("playlistItems.list")

    def get_videos_batch(self, video_ids: list[str]) -> list[dict[str, Any]]:
        """Get information for multiple videos in a single request.
        
        This is much more efficient than calling videos.list for each video.
        Costs only 1 quota unit for up to 50 videos.
        
        Args:
            video_ids: List of YouTube video IDs (max 50)
            
        Returns:
            List of video information dicts
        """
        if not video_ids:
            return []

        quota_tracker = get_quota_tracker()

        # YouTube API allows max 50 IDs per request
        batch_ids = video_ids[:50]

        try:
            response = (
                self.service.videos()
                .list(
                    part="snippet,contentDetails,status",
                    id=",".join(batch_ids),
                )
                .execute()
            )
            return response.get("items", [])
        except HttpError as e:
            logger.warning("Failed to get videos batch: %s", e)
            return []
        finally:
            # Track quota even if request fails
            quota_tracker.track("videos.list")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception(_is_retryable_error),
        reraise=True,
    )
    def upload_from_drive_with_retry(
        self,
        drive_file_id: str,
        metadata: VideoMetadata,
        progress_callback: Any | None = None,
    ) -> UploadResult:
        """Upload a video from Google Drive to YouTube with retry logic.

        This method wraps upload_from_drive with exponential backoff
        for handling quota/rate limit errors.

        Args:
            drive_file_id: Google Drive file ID
            metadata: Video metadata for YouTube
            progress_callback: Optional callback for progress updates

        Returns:
            UploadResult with video ID and URL
        """
        quota_tracker = get_quota_tracker()

        # Check if we have enough quota before attempting upload
        if not quota_tracker.can_perform("videos.insert"):
            logger.warning(
                "Insufficient quota for upload: remaining=%d, required=1600",
                quota_tracker.get_remaining_quota(),
            )

        logger.info(
            "Starting upload with retry: %s (quota remaining: %d)",
            drive_file_id,
            quota_tracker.get_remaining_quota(),
        )

        result = self.upload_from_drive(
            drive_file_id=drive_file_id,
            metadata=metadata,
            progress_callback=progress_callback,
        )

        # Track the upload operation
        if result.success:
            quota_tracker.track("videos.insert")

        return result


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
