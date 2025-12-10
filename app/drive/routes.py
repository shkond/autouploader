"""Google Drive routes."""

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import check_app_auth, get_current_user_from_session
from app.auth.oauth import get_oauth_service
from app.database import get_db
from app.drive.schemas import (
    DriveFile,
    FolderScanRequest,
    FolderScanResponse,
    FolderUploadRequest,
    FolderUploadResponse,
    SkippedFile,
)
from app.drive.service import DriveService

# Note: DriveService is instantiated per-request with user-specific credentials
from app.queue.manager_db import QueueManagerDB
from app.queue.schemas import QueueJob

router = APIRouter(prefix="/drive", tags=["google-drive"])



@router.get("/files", response_model=list[DriveFile])
async def list_files(
    folder_id: str = Query(default="root", description="Drive folder ID"),
    video_only: bool = Query(default=True, description="Filter to video files only"),
    session_token: str | None = Cookie(None, alias="session"),
) -> list[DriveFile]:
    """List files in a Drive folder.

    Args:
        folder_id: Google Drive folder ID (default: root)
        video_only: Whether to filter to video files only

    Returns:
        List of files in the folder
    """
    try:
        # Validate session and get user_id
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

        service = DriveService(credentials)
        return await service.list_files(folder_id, video_only)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list files: {e!s}",
        ) from e


@router.post("/scan", response_model=FolderScanResponse)
async def scan_folder(
    request: FolderScanRequest,
    session_token: str | None = Cookie(None, alias="session"),
) -> FolderScanResponse:
    """Scan a Drive folder for video files.

    Args:
        request: Folder scan request with options

    Returns:
        FolderScanResponse with folder contents
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

        service = DriveService(credentials)
        folder = await service.scan_folder(
            folder_id=request.folder_id,
            recursive=request.recursive,
            video_only=request.video_only,
        )
        return FolderScanResponse(
            folder=folder,
            message=f"Found {folder.total_videos} video(s) in folder",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to scan folder: {e!s}",
        ) from e


@router.get("/file/{file_id}")
async def get_file_info(file_id: str, session_token: str | None = Cookie(None, alias="session")) -> dict:
    """Get information about a specific file.

    Args:
        file_id: Google Drive file ID

    Returns:
        File metadata
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

        service = DriveService(credentials)
        return await service.get_file_metadata(file_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {e!s}",
        ) from e


@router.post("/folder/upload", response_model=FolderUploadResponse)
async def upload_folder(
    request: FolderUploadRequest,
    db: AsyncSession = Depends(get_db),
    session_token: str | None = Cookie(None, alias="session"),
) -> FolderUploadResponse:
    """Upload all videos from a Drive folder to YouTube.

    Scans the folder for video files and adds them to the upload queue.
    Supports duplicate detection via MD5 hash.

    Args:
        request: Folder upload request with settings
        db: Database session

    Returns:
        FolderUploadResponse with added and skipped file counts
    """
    import uuid
    from datetime import date

    from sqlalchemy import select

    from app.models import UploadHistory
    from app.queue.schemas import QueueJobCreate
    from app.youtube.schemas import PrivacyStatus, VideoMetadata

    try:
        # Get user ID from session
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
        drive_service = DriveService(credentials)

        # Get folder info
        if request.folder_id == "root":
            folder_name = "My Drive"
        else:
            folder_info = await drive_service.get_folder_info(request.folder_id)
            folder_name = folder_info["name"]

        # Generate batch ID
        batch_id = str(uuid.uuid4())

        # Get all videos in folder
        video_files = await drive_service.get_all_videos_flat(
            folder_id=request.folder_id,
            recursive=request.recursive,
            max_files=request.max_files,
        )

        added_jobs: list[QueueJob] = []
        skipped_files: list[SkippedFile] = []

        for file_meta, folder_path in video_files:
            file_id = file_meta["id"]
            file_name = file_meta["name"]
            md5_checksum = file_meta.get("md5Checksum", "")

            # Check for duplicates
            if request.skip_duplicates:
                # Check if already in queue
                if await QueueManagerDB.is_file_id_in_queue(db, file_id):
                    skipped_files.append(SkippedFile(
                        file_id=file_id,
                        file_name=file_name,
                        reason="already_in_queue",
                    ))
                    continue

                if md5_checksum and await QueueManagerDB.is_md5_in_queue(db, md5_checksum):
                    skipped_files.append(SkippedFile(
                        file_id=file_id,
                        file_name=file_name,
                        reason="duplicate_md5_in_queue",
                    ))
                    continue

                # Check if already uploaded (in database)
                if md5_checksum:
                    result = await db.execute(
                        select(UploadHistory).where(
                            UploadHistory.drive_md5_checksum == md5_checksum
                        )
                    )
                    existing = result.scalar_one_or_none()
                    if existing:
                        skipped_files.append(SkippedFile(
                            file_id=file_id,
                            file_name=file_name,
                            reason=f"already_uploaded:{existing.youtube_video_id}",
                        ))
                        continue

            # Generate video metadata from template
            settings = request.settings
            today = date.today().isoformat()

            # Remove file extension for title
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
            privacy = privacy_map.get(settings.default_privacy, PrivacyStatus.PRIVATE)

            video_metadata = VideoMetadata(
                title=title[:100],  # YouTube title limit
                description=description[:5000],  # YouTube description limit
                tags=settings.default_tags,
                category_id=settings.default_category_id,
                privacy_status=privacy,
                made_for_kids=settings.made_for_kids,
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

            job = await QueueManagerDB.add_job(db, job_create, user_id)
            added_jobs.append(job)

        return FolderUploadResponse(
            folder_name=folder_name,
            batch_id=batch_id,
            added_count=len(added_jobs),
            skipped_count=len(skipped_files),
            skipped_files=skipped_files,
            message=f"Added {len(added_jobs)} video(s) to queue, skipped {len(skipped_files)}",
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload folder: {e!s}",
        ) from e


