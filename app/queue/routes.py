"""Queue management routes."""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.config import get_settings
from app.core.dependencies import get_queue_repository, get_user_id_from_session
from app.queue.repositories import QueueRepository
from app.queue.schemas import (
    BulkQueueRequest,
    BulkQueueResponse,
    JobStatus,
    QueueJobCreate,
    QueueJobResponse,
    QueueListResponse,
    QueueStatus,
)
from app.queue.worker import get_queue_worker

router = APIRouter(prefix="/queue", tags=["upload-queue"])


def validate_file_size(file_size: int | None, file_name: str = "") -> tuple[bool, str]:
    """Validate file size against configured limits.

    Args:
        file_size: File size in bytes (None if unknown)
        file_name: Optional file name for error messages

    Returns:
        Tuple of (is_valid, warning_message)
        - is_valid: False if file exceeds max size
        - warning_message: Warning message if file exceeds warning size
    """
    if file_size is None:
        return True, ""

    settings = get_settings()

    if file_size > settings.max_file_size:
        size_gb = file_size / (1024 ** 3)
        max_gb = settings.max_file_size / (1024 ** 3)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size ({size_gb:.2f}GB) exceeds maximum allowed ({max_gb:.0f}GB)"
                   + (f": {file_name}" if file_name else ""),
        )

    if file_size > settings.warning_file_size:
        size_gb = file_size / (1024 ** 3)
        return True, f"Warning: Large file ({size_gb:.2f}GB)"

    return True, ""


@router.get("/status", response_model=QueueStatus)
async def get_queue_status(
    queue_repo: QueueRepository = Depends(get_queue_repository),
    user_id: str = Depends(get_user_id_from_session),
) -> QueueStatus:
    """Get overall queue status for the current user.

    Args:
        queue_repo: Queue repository (injected via DI)
        user_id: Current user ID (injected via DI)

    Returns:
        Queue status summary
    """
    return await queue_repo.get_status(user_id=user_id)


@router.get("/jobs", response_model=QueueListResponse)
async def list_jobs(
    queue_repo: QueueRepository = Depends(get_queue_repository),
    user_id: str = Depends(get_user_id_from_session),
) -> QueueListResponse:
    """List all jobs in the queue for the current user.

    Args:
        queue_repo: Queue repository (injected via DI)
        user_id: Current user ID (injected via DI)

    Returns:
        List of user's queue jobs with status
    """
    jobs = await queue_repo.get_jobs_by_user(user_id)
    # Sort by created_at (newest first)
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    queue_status = await queue_repo.get_status(user_id=user_id)
    return QueueListResponse(jobs=jobs, status=queue_status)


@router.post("/jobs", response_model=QueueJobResponse)
async def add_job(
    job_create: QueueJobCreate,
    background_tasks: BackgroundTasks,
    queue_repo: QueueRepository = Depends(get_queue_repository),
    user_id: str = Depends(get_user_id_from_session),
) -> QueueJobResponse:
    """Add a new job to the upload queue.

    Args:
        job_create: Job creation request
        background_tasks: FastAPI background tasks
        queue_repo: Queue repository (injected via DI)
        user_id: Current user ID (injected via DI)

    Returns:
        Created job

    Raises:
        HTTPException: If file size exceeds maximum limit
    """
    # Validate file size
    _, warning = validate_file_size(job_create.file_size, job_create.drive_file_name)

    job = await queue_repo.add_job(job_create, user_id)

    # Ensure worker is running
    worker = get_queue_worker()
    if not worker.is_running():
        background_tasks.add_task(_start_worker)

    message = warning if warning else "Job added to queue"
    return QueueJobResponse(job=job, message=message)


@router.post("/jobs/bulk", response_model=BulkQueueResponse)
async def add_bulk_jobs(
    request: BulkQueueRequest,
    background_tasks: BackgroundTasks,
    queue_repo: QueueRepository = Depends(get_queue_repository),
    user_id: str = Depends(get_user_id_from_session),
) -> BulkQueueResponse:
    """Add multiple jobs to the upload queue.

    Args:
        request: Bulk queue request with multiple files
        background_tasks: FastAPI background tasks
        queue_repo: Queue repository (injected via DI)
        user_id: Current user ID (injected via DI)

    Returns:
        Bulk operation response

    Raises:
        HTTPException: If any file size exceeds maximum limit
    """
    # Validate all file sizes first
    warnings = []
    for file_job in request.files:
        _, warning = validate_file_size(file_job.file_size, file_job.drive_file_name)
        if warning:
            warnings.append(warning)

    jobs = []
    for file_job in request.files:
        job = await queue_repo.add_job(file_job, user_id)
        jobs.append(job)

    # Ensure worker is running
    worker = get_queue_worker()
    if not worker.is_running():
        background_tasks.add_task(_start_worker)

    message = f"Added {len(jobs)} job(s) to queue"
    if warnings:
        message += f" ({len(warnings)} large file warning(s))"

    return BulkQueueResponse(
        added_count=len(jobs),
        jobs=jobs,
        message=message,
    )


@router.get("/jobs/{job_id}", response_model=QueueJobResponse)
async def get_job(
    job_id: UUID,
    queue_repo: QueueRepository = Depends(get_queue_repository),
    user_id: str = Depends(get_user_id_from_session),
) -> QueueJobResponse:
    """Get a specific job by ID.

    Args:
        job_id: Job UUID
        queue_repo: Queue repository (injected via DI)
        user_id: Current user ID (injected via DI)

    Returns:
        Job details

    Raises:
        HTTPException: If job not found or doesn't belong to user
    """
    job = await queue_repo.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    # Verify job belongs to user
    if job.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return QueueJobResponse(job=job)


@router.post("/jobs/{job_id}/cancel", response_model=QueueJobResponse)
async def cancel_job(
    job_id: UUID,
    queue_repo: QueueRepository = Depends(get_queue_repository),
    user_id: str = Depends(get_user_id_from_session),
) -> QueueJobResponse:
    """Cancel a pending job.

    Args:
        job_id: Job UUID
        queue_repo: Queue repository (injected via DI)
        user_id: Current user ID (injected via DI)

    Returns:
        Cancelled job

    Raises:
        HTTPException: If job not found, doesn't belong to user, or cannot be cancelled
    """
    # Verify job belongs to user
    job = await queue_repo.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    if job.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # Cancel the job
    cancelled_job = await queue_repo.cancel_job(job_id)
    if not cancelled_job:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job cannot be cancelled",
        )

    return QueueJobResponse(job=cancelled_job, message="Job cancelled")


@router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: UUID,
    queue_repo: QueueRepository = Depends(get_queue_repository),
    user_id: str = Depends(get_user_id_from_session),
) -> dict:
    """Delete a job from the queue.

    Args:
        job_id: Job UUID
        queue_repo: Queue repository (injected via DI)
        user_id: Current user ID (injected via DI)

    Returns:
        Success message

    Raises:
        HTTPException: If job not found, doesn't belong to user, or is active
    """
    job = await queue_repo.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    # Verify job belongs to user
    if job.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    if job.status in (JobStatus.DOWNLOADING, JobStatus.UPLOADING):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete an active job. Cancel it first.",
        )

    await queue_repo.delete_job(job_id)
    return {"message": "Job deleted"}


@router.post("/clear")
async def clear_completed(
    queue_repo: QueueRepository = Depends(get_queue_repository),
    user_id: str = Depends(get_user_id_from_session),
) -> dict:
    """Clear all completed, failed, and cancelled jobs for the current user.

    Args:
        queue_repo: Queue repository (injected via DI)
        user_id: Current user ID (injected via DI)

    Returns:
        Number of jobs cleared
    """
    count = await queue_repo.clear_completed(user_id=user_id)
    return {"message": f"Cleared {count} job(s)", "cleared_count": count}


async def _start_worker() -> None:
    """Start the queue worker (used as background task for auto-start).
    
    Note: In production, the worker runs as a separate Heroku dyno.
    This function is kept for local development auto-start when jobs are added.
    """
    worker = get_queue_worker()
    await worker.start()
