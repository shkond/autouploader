"""API routes for schedule settings management."""

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import get_user_id_from_session
from app.database import get_db
from app.settings.repositories import ScheduleSettingsRepository
from app.settings.schemas import (
    FolderValidationRequest,
    FolderValidationResponse,
    ScheduleSettingsCreate,
    ScheduleSettingsResponse,
    ScheduleSettingsUpdate,
    extract_folder_id,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


async def get_schedule_repository(
    db: "AsyncSession" = Depends(get_db),
) -> ScheduleSettingsRepository:
    """Dependency to get schedule settings repository."""
    return ScheduleSettingsRepository(db)


@router.get("/schedule", response_model=ScheduleSettingsResponse | None)
async def get_schedule_settings(
    repo: ScheduleSettingsRepository = Depends(get_schedule_repository),
    user_id: str = Depends(get_user_id_from_session),
) -> ScheduleSettingsResponse | None:
    """Get current user's schedule settings.
    
    Returns:
        Schedule settings or None if not configured
    """
    settings = await repo.get_by_user_id(user_id)
    if not settings:
        return None
    
    return ScheduleSettingsResponse(
        id=settings.id,
        user_id=settings.user_id,
        folder_url=settings.folder_url,
        folder_id=settings.folder_id,
        max_files_per_run=settings.max_files_per_run,
        title_template=settings.title_template,
        description_template=settings.description_template,
        default_privacy=settings.default_privacy,
        recursive=settings.recursive,
        skip_duplicates=settings.skip_duplicates,
        include_md5_hash=settings.include_md5_hash,
        is_enabled=settings.is_enabled,
        created_at=settings.created_at.isoformat(),
        updated_at=settings.updated_at.isoformat(),
    )


@router.post("/schedule", response_model=ScheduleSettingsResponse)
async def save_schedule_settings(
    request: ScheduleSettingsCreate,
    repo: ScheduleSettingsRepository = Depends(get_schedule_repository),
    user_id: str = Depends(get_user_id_from_session),
) -> ScheduleSettingsResponse:
    """Create or update schedule settings for the current user.
    
    Args:
        request: Schedule settings to save
        
    Returns:
        Saved schedule settings
    """
    # Extract folder ID from URL
    folder_id = extract_folder_id(request.folder_url)
    if not folder_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not extract folder ID from URL",
        )
    
    # Check if user already has settings
    existing = await repo.get_by_user_id(user_id)
    
    if existing:
        # Update existing settings
        settings = await repo.update(
            existing,
            folder_url=request.folder_url,
            folder_id=folder_id,
            max_files_per_run=request.max_files_per_run,
            title_template=request.title_template,
            description_template=request.description_template,
            default_privacy=request.default_privacy,
            recursive=request.recursive,
            skip_duplicates=request.skip_duplicates,
            include_md5_hash=request.include_md5_hash,
            is_enabled=request.is_enabled,
        )
        logger.info("Updated schedule settings for user: %s", user_id)
    else:
        # Create new settings
        settings = await repo.create(
            user_id=user_id,
            folder_url=request.folder_url,
            folder_id=folder_id,
            max_files_per_run=request.max_files_per_run,
            title_template=request.title_template,
            description_template=request.description_template,
            default_privacy=request.default_privacy,
            recursive=request.recursive,
            skip_duplicates=request.skip_duplicates,
            include_md5_hash=request.include_md5_hash,
            is_enabled=request.is_enabled,
        )
        logger.info("Created schedule settings for user: %s", user_id)
    
    return ScheduleSettingsResponse(
        id=settings.id,
        user_id=settings.user_id,
        folder_url=settings.folder_url,
        folder_id=settings.folder_id,
        max_files_per_run=settings.max_files_per_run,
        title_template=settings.title_template,
        description_template=settings.description_template,
        default_privacy=settings.default_privacy,
        recursive=settings.recursive,
        skip_duplicates=settings.skip_duplicates,
        include_md5_hash=settings.include_md5_hash,
        is_enabled=settings.is_enabled,
        created_at=settings.created_at.isoformat(),
        updated_at=settings.updated_at.isoformat(),
    )


@router.patch("/schedule", response_model=ScheduleSettingsResponse)
async def update_schedule_settings(
    request: ScheduleSettingsUpdate,
    repo: ScheduleSettingsRepository = Depends(get_schedule_repository),
    user_id: str = Depends(get_user_id_from_session),
) -> ScheduleSettingsResponse:
    """Partially update schedule settings for the current user.
    
    Args:
        request: Fields to update (only provided fields are updated)
        
    Returns:
        Updated schedule settings
    """
    existing = await repo.get_by_user_id(user_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule settings not found. Use POST to create.",
        )
    
    update_data = request.model_dump(exclude_unset=True)
    
    # Extract folder ID if URL is being updated
    if "folder_url" in update_data:
        folder_id = extract_folder_id(update_data["folder_url"])
        if not folder_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not extract folder ID from URL",
            )
        update_data["folder_id"] = folder_id
    
    settings = await repo.update(existing, **update_data)
    logger.info("Patched schedule settings for user: %s", user_id)
    
    return ScheduleSettingsResponse(
        id=settings.id,
        user_id=settings.user_id,
        folder_url=settings.folder_url,
        folder_id=settings.folder_id,
        max_files_per_run=settings.max_files_per_run,
        title_template=settings.title_template,
        description_template=settings.description_template,
        default_privacy=settings.default_privacy,
        recursive=settings.recursive,
        skip_duplicates=settings.skip_duplicates,
        include_md5_hash=settings.include_md5_hash,
        is_enabled=settings.is_enabled,
        created_at=settings.created_at.isoformat(),
        updated_at=settings.updated_at.isoformat(),
    )


@router.delete("/schedule")
async def delete_schedule_settings(
    repo: ScheduleSettingsRepository = Depends(get_schedule_repository),
    user_id: str = Depends(get_user_id_from_session),
) -> dict:
    """Delete schedule settings for the current user.
    
    Returns:
        Success message
    """
    existing = await repo.get_by_user_id(user_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule settings not found",
        )
    
    await repo.delete(existing)
    logger.info("Deleted schedule settings for user: %s", user_id)
    
    return {"message": "Schedule settings deleted successfully"}


@router.post("/schedule/validate-folder", response_model=FolderValidationResponse)
async def validate_folder(
    request: FolderValidationRequest,
    user_id: str = Depends(get_user_id_from_session),
) -> FolderValidationResponse:
    """Validate a Google Drive folder URL and check access.
    
    Args:
        request: Folder URL to validate
        
    Returns:
        Validation result with folder info if valid
    """
    # Extract folder ID
    folder_id = extract_folder_id(request.folder_url)
    if not folder_id:
        return FolderValidationResponse(
            valid=False,
            error="Invalid Google Drive folder URL format",
        )
    
    # Try to access the folder via Drive API
    try:
        from app.auth.oauth import get_oauth_service
        from app.drive.services import DriveService
        
        oauth_service = get_oauth_service()
        credentials = await oauth_service.get_credentials(user_id)
        
        if not credentials:
            return FolderValidationResponse(
                valid=False,
                folder_id=folder_id,
                error="Google account not authenticated",
            )
        
        drive_service = DriveService(credentials=credentials)
        folder_info = await drive_service.get_folder_info(folder_id)
        
        return FolderValidationResponse(
            valid=True,
            folder_id=folder_id,
            folder_name=folder_info.get("name"),
        )
    except Exception as e:
        logger.warning("Folder validation failed for %s: %s", folder_id, e)
        return FolderValidationResponse(
            valid=False,
            folder_id=folder_id,
            error=f"Cannot access folder: {e!s}",
        )
