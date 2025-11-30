"""Pydantic schemas for YouTube."""

from enum import Enum

from pydantic import BaseModel, Field


class PrivacyStatus(str, Enum):
    """YouTube video privacy status."""

    PUBLIC = "public"
    PRIVATE = "private"
    UNLISTED = "unlisted"


class VideoCategory(str, Enum):
    """Common YouTube video categories."""

    FILM_ANIMATION = "1"
    AUTOS_VEHICLES = "2"
    MUSIC = "10"
    PETS_ANIMALS = "15"
    SPORTS = "17"
    GAMING = "20"
    PEOPLE_BLOGS = "22"
    COMEDY = "23"
    ENTERTAINMENT = "24"
    NEWS_POLITICS = "25"
    HOWTO_STYLE = "26"
    EDUCATION = "27"
    SCIENCE_TECH = "28"
    NONPROFITS_ACTIVISM = "29"


class VideoMetadata(BaseModel):
    """YouTube video metadata for upload."""

    title: str = Field(..., max_length=100, description="Video title")
    description: str = Field(
        default="", max_length=5000, description="Video description"
    )
    tags: list[str] = Field(
        default_factory=list, max_length=500, description="Video tags"
    )
    category_id: str = Field(
        default=VideoCategory.ENTERTAINMENT, description="YouTube category ID"
    )
    privacy_status: PrivacyStatus = Field(
        default=PrivacyStatus.PRIVATE, description="Video privacy status"
    )
    made_for_kids: bool = Field(
        default=False, description="Whether the video is made for kids"
    )
    notify_subscribers: bool = Field(
        default=False, description="Whether to notify subscribers"
    )


class UploadRequest(BaseModel):
    """Request to upload a video from Drive to YouTube."""

    drive_file_id: str = Field(..., description="Google Drive file ID")
    metadata: VideoMetadata


class UploadProgress(BaseModel):
    """Upload progress information."""

    file_id: str
    status: str
    progress: float = Field(default=0.0, ge=0, le=100)
    bytes_uploaded: int = 0
    total_bytes: int = 0
    message: str = ""


class UploadResult(BaseModel):
    """Result of a YouTube upload."""

    success: bool
    video_id: str | None = None
    video_url: str | None = None
    message: str
    error: str | None = None


class YouTubeVideo(BaseModel):
    """YouTube video information."""

    id: str
    title: str
    description: str | None = None
    thumbnail_url: str | None = None
    channel_id: str | None = None
    published_at: str | None = None
    view_count: int | None = None
