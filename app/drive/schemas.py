"""Pydantic schemas for Google Drive."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class FileType(str, Enum):
    """File type enum."""

    VIDEO = "video"
    FOLDER = "folder"
    OTHER = "other"


class DriveFile(BaseModel):
    """Google Drive file information."""

    id: str
    name: str
    mime_type: str = Field(alias="mimeType")
    size: int | None = None
    created_time: datetime | None = Field(None, alias="createdTime")
    modified_time: datetime | None = Field(None, alias="modifiedTime")
    file_type: FileType = FileType.OTHER
    parent_id: str | None = None
    thumbnail_link: str | None = Field(None, alias="thumbnailLink")
    web_view_link: str | None = Field(None, alias="webViewLink")

    model_config = {"populate_by_name": True}


class DriveFolder(BaseModel):
    """Google Drive folder information."""

    id: str
    name: str
    files: list[DriveFile] = Field(default_factory=list)
    subfolders: list["DriveFolder"] = Field(default_factory=list)
    total_videos: int = 0


class FolderScanRequest(BaseModel):
    """Request to scan a Drive folder."""

    folder_id: str = Field(..., description="Google Drive folder ID")
    recursive: bool = Field(
        default=False, description="Whether to scan subfolders recursively"
    )
    video_only: bool = Field(
        default=True, description="Filter to show only video files"
    )


class FolderScanResponse(BaseModel):
    """Response from folder scan."""

    folder: DriveFolder
    message: str = "Scan completed"


# Update forward references
DriveFolder.model_rebuild()
