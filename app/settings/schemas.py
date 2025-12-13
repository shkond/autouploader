"""Pydantic schemas for schedule settings."""

import re

from pydantic import BaseModel, Field, field_validator


class ScheduleSettingsBase(BaseModel):
    """Base schema for schedule settings."""

    folder_url: str = Field(
        ...,
        description="Full Google Drive folder URL",
        examples=["https://drive.google.com/drive/folders/abc123"],
    )
    max_files_per_run: int = Field(
        default=50,
        ge=1,
        le=100,
        description="Maximum files to process per scheduler run",
    )
    title_template: str = Field(
        default="{filename}",
        max_length=200,
        description="Template for video title",
    )
    description_template: str = Field(
        default="Uploaded from {folder_path}",
        description="Template for video description",
    )
    default_privacy: str = Field(
        default="private",
        description="Default privacy status",
    )
    recursive: bool = Field(
        default=True,
        description="Include subfolders when scanning",
    )
    skip_duplicates: bool = Field(
        default=True,
        description="Skip already uploaded files",
    )
    include_md5_hash: bool = Field(
        default=True,
        description="Add MD5 hash to video description",
    )
    is_enabled: bool = Field(
        default=True,
        description="Enable/disable this schedule",
    )

    @field_validator("folder_url")
    @classmethod
    def validate_folder_url(cls, v: str) -> str:
        """Validate and normalize Google Drive folder URL."""
        if not v or not v.strip():
            raise ValueError("Folder URL cannot be empty")
        
        # Normalize URL
        v = v.strip()
        
        # Check for valid Google Drive folder URL patterns
        patterns = [
            r"https?://drive\.google\.com/drive/(?:u/\d+/)?folders/([a-zA-Z0-9_-]+)",
            r"https?://drive\.google\.com/drive/folders/([a-zA-Z0-9_-]+)",
        ]
        
        for pattern in patterns:
            if re.search(pattern, v):
                return v
        
        raise ValueError(
            "Invalid Google Drive folder URL. "
            "Expected format: https://drive.google.com/drive/folders/{folder_id}"
        )

    @field_validator("default_privacy")
    @classmethod
    def validate_privacy(cls, v: str) -> str:
        """Validate privacy status."""
        allowed = {"private", "unlisted", "public"}
        if v not in allowed:
            raise ValueError(f"Privacy must be one of: {allowed}")
        return v


class ScheduleSettingsCreate(ScheduleSettingsBase):
    """Schema for creating schedule settings."""

    pass


class ScheduleSettingsUpdate(BaseModel):
    """Schema for updating schedule settings (all fields optional)."""

    folder_url: str | None = None
    max_files_per_run: int | None = Field(default=None, ge=1, le=100)
    title_template: str | None = Field(default=None, max_length=200)
    description_template: str | None = None
    default_privacy: str | None = None
    recursive: bool | None = None
    skip_duplicates: bool | None = None
    include_md5_hash: bool | None = None
    is_enabled: bool | None = None

    @field_validator("folder_url")
    @classmethod
    def validate_folder_url(cls, v: str | None) -> str | None:
        """Validate folder URL if provided."""
        if v is None:
            return None
        return ScheduleSettingsBase.validate_folder_url(v)

    @field_validator("default_privacy")
    @classmethod
    def validate_privacy(cls, v: str | None) -> str | None:
        """Validate privacy if provided."""
        if v is None:
            return None
        return ScheduleSettingsBase.validate_privacy(v)


class ScheduleSettingsResponse(ScheduleSettingsBase):
    """Schema for schedule settings response."""

    id: int
    user_id: str
    folder_id: str
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class FolderValidationRequest(BaseModel):
    """Request to validate a folder URL."""

    folder_url: str = Field(..., description="Google Drive folder URL to validate")


class FolderValidationResponse(BaseModel):
    """Response from folder validation."""

    valid: bool
    folder_id: str | None = None
    folder_name: str | None = None
    error: str | None = None


def extract_folder_id(url: str) -> str | None:
    """Extract folder ID from Google Drive URL.
    
    Args:
        url: Google Drive folder URL
        
    Returns:
        Folder ID or None if invalid
    """
    patterns = [
        r"https?://drive\.google\.com/drive/(?:u/\d+/)?folders/([a-zA-Z0-9_-]+)",
        r"https?://drive\.google\.com/drive/folders/([a-zA-Z0-9_-]+)",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None
