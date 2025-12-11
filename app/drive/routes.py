"""Google Drive routes."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_drive_service,
    get_user_id_from_session,
)
from app.database import get_db
from app.drive.schemas import (
    DriveFile,
    FolderScanRequest,
    FolderScanResponse,
    FolderUploadRequest,
    FolderUploadResponse,
)
from app.drive.services import DriveService

router = APIRouter(prefix="/drive", tags=["google-drive"])


@router.get("/files", response_model=list[DriveFile])
async def list_files(
    folder_id: str = Query(default="root", description="Drive folder ID"),
    video_only: bool = Query(default=True, description="Filter to video files only"),
    service: DriveService = Depends(get_drive_service),
) -> list[DriveFile]:
    """List files in a Drive folder.

    Args:
        folder_id: Google Drive folder ID (default: root)
        video_only: Whether to filter to video files only
        service: DriveService (injected via DI)

    Returns:
        List of files in the folder
    """
    try:
        return await service.list_files(folder_id, video_only)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list files: {e!s}",
        ) from e


@router.post("/scan", response_model=FolderScanResponse)
async def scan_folder(
    request: FolderScanRequest,
    service: DriveService = Depends(get_drive_service),
) -> FolderScanResponse:
    """Scan a Drive folder for video files.

    Args:
        request: Folder scan request with options
        service: DriveService (injected via DI)

    Returns:
        FolderScanResponse with folder contents
    """
    try:
        folder = await service.scan_folder(
            folder_id=request.folder_id,
            recursive=request.recursive,
            video_only=request.video_only,
        )
        return FolderScanResponse(
            folder=folder,
            message=f"Found {folder.total_videos} video(s) in folder",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to scan folder: {e!s}",
        ) from e


@router.get("/file/{file_id}")
async def get_file_info(
    file_id: str,
    service: DriveService = Depends(get_drive_service),
) -> dict:
    """Get information about a specific file.

    Args:
        file_id: Google Drive file ID
        service: DriveService (injected via DI)

    Returns:
        File metadata
    """
    try:
        return await service.get_file_metadata(file_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {e!s}",
        ) from e


@router.post("/folder/upload", response_model=FolderUploadResponse)
async def upload_folder(
    request: FolderUploadRequest,
    service: DriveService = Depends(get_drive_service),
    user_id: str = Depends(get_user_id_from_session),
    db: AsyncSession = Depends(get_db),
) -> FolderUploadResponse:
    """Upload all videos from a Drive folder to YouTube.

    Scans the folder for video files and adds them to the upload queue.
    Supports duplicate detection via MD5 hash.

    Args:
        request: Folder upload request with settings
        service: DriveService (injected via DI)
        user_id: Current user ID (injected via DI)
        db: Database session

    Returns:
        FolderUploadResponse with added and skipped file counts
    """
    from app.tasks.services import FolderUploadService

    try:
        folder_service = FolderUploadService(service, db)

        result = await folder_service.process_folder(
            folder_id=request.folder_id,
            user_id=user_id,
            settings=request.settings,
            recursive=request.recursive,
            max_files=request.max_files,
            skip_duplicates=request.skip_duplicates,
        )

        return FolderUploadResponse(
            folder_name=result.folder_name,
            batch_id=result.batch_id,
            added_count=len(result.added_jobs),
            skipped_count=len(result.skipped_files),
            skipped_files=result.skipped_files,
            message=f"Added {len(result.added_jobs)} video(s) to queue, skipped {len(result.skipped_files)}",
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload folder: {e!s}",
        ) from e



