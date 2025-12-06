"""Pydantic schemas for upload queue."""

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.youtube.schemas import VideoMetadata


class JobStatus(str, Enum):
    """Upload job status."""

    PENDING = "pending"
    DOWNLOADING = "downloading"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class QueueJob(BaseModel):
    """Upload queue job."""

    id: UUID = Field(default_factory=uuid4)
    user_id: str = Field(default="", description="User who created this job")
    drive_file_id: str
    drive_file_name: str
    drive_md5_checksum: str | None = None
    folder_path: str | None = None
    batch_id: str | None = None
    metadata: VideoMetadata
    status: JobStatus = JobStatus.PENDING
    progress: float = Field(default=0.0, ge=0, le=100)
    message: str = ""
    video_id: str | None = None
    video_url: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    retry_count: int = 0
    max_retries: int = 3


class QueueJobCreate(BaseModel):
    """Request to create a queue job."""

    drive_file_id: str = Field(..., description="Google Drive file ID")
    drive_file_name: str = Field(..., description="Original file name")
    drive_md5_checksum: str | None = Field(None, description="MD5 checksum for deduplication")
    folder_path: str | None = Field(None, description="Folder path in Drive")
    batch_id: str | None = Field(None, description="Batch ID for grouping jobs")
    metadata: VideoMetadata



class QueueJobResponse(BaseModel):
    """Response for a queue job."""

    job: QueueJob
    message: str = ""


class QueueStatus(BaseModel):
    """Overall queue status."""

    total_jobs: int = 0
    pending_jobs: int = 0
    active_jobs: int = 0
    completed_jobs: int = 0
    failed_jobs: int = 0
    is_processing: bool = False


class QueueListResponse(BaseModel):
    """Response for listing queue jobs."""

    jobs: list[QueueJob] = Field(default_factory=list)
    status: QueueStatus


class BulkQueueRequest(BaseModel):
    """Request to add multiple files to queue."""

    files: list[QueueJobCreate] = Field(..., min_length=1)


class BulkQueueResponse(BaseModel):
    """Response for bulk queue operation."""

    added_count: int
    jobs: list[QueueJob] = Field(default_factory=list)
    message: str = ""
