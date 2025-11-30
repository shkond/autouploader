"""YouTube routes."""

from fastapi import APIRouter, HTTPException, Query, status

from app.youtube.schemas import UploadRequest, UploadResult, YouTubeVideo
from app.youtube.service import get_youtube_service

router = APIRouter(prefix="/youtube", tags=["youtube"])


@router.get("/channel")
async def get_channel_info() -> dict:
    """Get authenticated user's YouTube channel information.

    Returns:
        Channel information
    """
    try:
        service = get_youtube_service()
        return service.get_channel_info()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get channel info: {e!s}",
        ) from e


@router.get("/videos", response_model=list[YouTubeVideo])
async def list_my_videos(
    max_results: int = Query(
        default=25, ge=1, le=50, description="Max videos to return"
    ),
) -> list[YouTubeVideo]:
    """List videos uploaded by the authenticated user.

    Args:
        max_results: Maximum number of videos to return

    Returns:
        List of YouTube videos
    """
    try:
        service = get_youtube_service()
        items = service.list_my_videos(max_results)
        videos = []
        for item in items:
            snippet = item.get("snippet", {})
            video_id = item.get("id", {}).get("videoId", "")
            thumbnails = snippet.get("thumbnails", {})
            thumbnail_url = thumbnails.get("default", {}).get("url")

            videos.append(
                YouTubeVideo(
                    id=video_id,
                    title=snippet.get("title", ""),
                    description=snippet.get("description"),
                    thumbnail_url=thumbnail_url,
                    channel_id=snippet.get("channelId"),
                    published_at=snippet.get("publishedAt"),
                )
            )
        return videos
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list videos: {e!s}",
        ) from e


@router.post("/upload", response_model=UploadResult)
async def upload_video(request: UploadRequest) -> UploadResult:
    """Upload a video from Google Drive to YouTube.

    This is a synchronous upload endpoint. For large files or
    multiple uploads, use the queue system instead.

    Args:
        request: Upload request with Drive file ID and metadata

    Returns:
        Upload result with video ID and URL
    """
    try:
        service = get_youtube_service()
        result = service.upload_from_drive(
            drive_file_id=request.drive_file_id,
            metadata=request.metadata,
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload failed: {e!s}",
        ) from e
