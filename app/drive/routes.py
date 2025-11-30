"""Google Drive routes."""

from fastapi import APIRouter, HTTPException, Query, status

from app.drive.schemas import DriveFile, FolderScanRequest, FolderScanResponse
from app.drive.service import get_drive_service

router = APIRouter(prefix="/drive", tags=["google-drive"])


@router.get("/files", response_model=list[DriveFile])
async def list_files(
    folder_id: str = Query(default="root", description="Drive folder ID"),
    video_only: bool = Query(default=True, description="Filter to video files only"),
) -> list[DriveFile]:
    """List files in a Drive folder.

    Args:
        folder_id: Google Drive folder ID (default: root)
        video_only: Whether to filter to video files only

    Returns:
        List of files in the folder
    """
    try:
        service = get_drive_service()
        return service.list_files(folder_id, video_only)
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
async def scan_folder(request: FolderScanRequest) -> FolderScanResponse:
    """Scan a Drive folder for video files.

    Args:
        request: Folder scan request with options

    Returns:
        FolderScanResponse with folder contents
    """
    try:
        service = get_drive_service()
        folder = service.scan_folder(
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
async def get_file_info(file_id: str) -> dict:
    """Get information about a specific file.

    Args:
        file_id: Google Drive file ID

    Returns:
        File metadata
    """
    try:
        service = get_drive_service()
        return service.get_file_metadata(file_id)
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
