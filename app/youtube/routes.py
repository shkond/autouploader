"""YouTube routes."""

from fastapi import APIRouter, Cookie, HTTPException, Query, status

from app.auth.dependencies import check_app_auth, get_current_user_from_session
from app.auth.oauth import get_oauth_service
from app.youtube.quota import get_quota_tracker
from app.youtube.schemas import UploadRequest, UploadResult, YouTubeVideo
from app.youtube.service import YouTubeService

router = APIRouter(prefix="/youtube", tags=["youtube"])


@router.get("/channel")
async def get_channel_info(session_token: str | None = Cookie(None, alias="session")) -> dict:
    """Get authenticated user's YouTube channel information.

    Returns:
        Channel information
    """
    try:
        session_data = check_app_auth(session_token)
        if not session_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        user_id = get_current_user_from_session(session_data)

        oauth_service = get_oauth_service()
        credentials = await oauth_service.get_credentials(user_id)
        if not credentials:
            raise ValueError("Not authenticated with Google")
        service = YouTubeService(credentials)
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
    session_token: str | None = Cookie(None, alias="session"),
) -> list[YouTubeVideo]:
    """List videos uploaded by the authenticated user.

    Args:
        max_results: Maximum number of videos to return

    Returns:
        List of YouTube videos
    """
    try:
        session_data = check_app_auth(session_token)
        if not session_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        user_id = get_current_user_from_session(session_data)

        oauth_service = get_oauth_service()
        credentials = await oauth_service.get_credentials(user_id)
        if not credentials:
            raise ValueError("Not authenticated with Google")
        service = YouTubeService(credentials)
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
async def upload_video(request: UploadRequest, session_token: str | None = Cookie(None, alias="session")) -> UploadResult:
    """Upload a video from Google Drive to YouTube.

    This is a synchronous upload endpoint. For large files or
    multiple uploads, use the queue system instead.

    Args:
        request: Upload request with Drive file ID and metadata

    Returns:
        Upload result with video ID and URL
    """
    try:
        session_data = check_app_auth(session_token)
        if not session_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        user_id = get_current_user_from_session(session_data)

        oauth_service = get_oauth_service()
        credentials = await oauth_service.get_credentials(user_id)
        if not credentials:
            raise ValueError("Not authenticated with Google")
        service = YouTubeService(credentials)
        result = await service.upload_from_drive_async(
            drive_file_id=request.drive_file_id,
            metadata=request.metadata,
            drive_credentials=credentials,
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


@router.get("/quota")
async def get_quota_status() -> dict:
    """Get current YouTube API quota usage status.

    Returns:
        Quota usage summary including daily usage, remaining quota,
        and breakdown by API operation.
    """
    tracker = get_quota_tracker()
    return tracker.get_usage_summary()


@router.get("/video/{video_id}/exists")
async def check_video_exists(video_id: str, session_token: str | None = Cookie(None, alias="session")) -> dict:
    """Check if a video exists on YouTube.

    This is useful for verifying that previously uploaded videos still exist.
    Costs only 1 quota unit.

    Args:
        video_id: YouTube video ID to check

    Returns:
        Dict with exists boolean and video_id
    """
    try:
        session_data = check_app_auth(session_token)
        if not session_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        user_id = get_current_user_from_session(session_data)

        oauth_service = get_oauth_service()
        credentials = await oauth_service.get_credentials(user_id)
        if not credentials:
            raise ValueError("Not authenticated with Google")
        service = YouTubeService(credentials)
        exists = service.check_video_exists_on_youtube(video_id)
        return {"video_id": video_id, "exists": exists}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check video: {e!s}",
        ) from e
