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


class QueueJobBase(BaseModel):
    """Base class for queue job schemas.
    
    Contains common fields shared between QueueJobCreate, QueueJob, and QueueJobModel.
    This ensures field synchronization and prevents missing field bugs.
    
    Note: When adding a new field here, also add it to QueueJobModel in models.py
    and update the _model_to_schema method in repositories.py.
    """

    drive_file_id: str = Field(..., description="Google Drive file ID")
    drive_file_name: str = Field(..., description="Original file name")
    drive_md5_checksum: str | None = Field(None, description="MD5 checksum for deduplication")
    file_size: int | None = Field(None, description="File size in bytes for validation")
    folder_path: str | None = Field(None, description="Folder path in Drive")
    batch_id: str | None = Field(None, description="Batch ID for grouping jobs")


# Fields that should exist in both QueueJob schema and QueueJobModel
# Used by synchronization tests to verify consistency
QUEUE_JOB_SHARED_FIELDS: set[str] = {
    "id",
    "user_id",
    "drive_file_id",
    "drive_file_name",
    "drive_md5_checksum",
    "file_size",
    "folder_path",
    "batch_id",
    "status",
    "progress",
    "message",
    "video_id",
    "video_url",
    "error",
    "retry_count",
    "max_retries",
    "created_at",
    "updated_at",
    "started_at",
    "completed_at",
}

# Fields in QueueJobCreate that map to QueueJobModel
# (metadata -> metadata_json is handled separately)
QUEUE_JOB_CREATE_FIELDS: set[str] = {
    "drive_file_id",
    "drive_file_name",
    "drive_md5_checksum",
    "file_size",
    "folder_path",
    "batch_id",
}


class QueueJobCreate(QueueJobBase):
    """Request to create a queue job.
    
    Inherits common fields from QueueJobBase.
    Only includes fields that clients should provide when creating a job.
    """

    metadata: VideoMetadata = Field(..., description="Video metadata for YouTube upload")


class QueueJob(QueueJobBase):
    """Upload queue job response schema.
    
    Inherits common fields from QueueJobBase.
    Includes all fields returned to clients, including server-generated fields.
    """

    id: UUID = Field(default_factory=uuid4)
    user_id: str = Field(default="", description="User who created this job")
    metadata: VideoMetadata
    status: JobStatus = JobStatus.PENDING
    progress: float = Field(default=0.0, ge=0, le=100)
    message: str = ""
    video_id: str | None = None
    video_url: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    retry_count: int = 0
    max_retries: int = 3


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
