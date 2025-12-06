"""Queue management routes."""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import check_app_auth, get_current_user_from_session
from app.database import get_db
from app.queue.manager_db import QueueManagerDB
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


async def get_current_user_id(
    session_token: str | None = Cookie(None, alias="session"),
) -> str:
    """Get current user ID from session.
    
    Args:
        session_token: Session cookie
        
    Returns:
        User ID string
        
    Raises:
        HTTPException: If not authenticated
    """
    session_data = check_app_auth(session_token)
    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    return get_current_user_from_session(session_data)


@router.get("/status", response_model=QueueStatus)
async def get_queue_status(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> QueueStatus:
    """Get overall queue status for the current user.

    Args:
        db: Database session
        user_id: Current user ID

    Returns:
        Queue status summary
    """
    return await QueueManagerDB.get_status(db, user_id=user_id)


@router.get("/jobs", response_model=QueueListResponse)
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> QueueListResponse:
    """List all jobs in the queue for the current user.

    Args:
        db: Database session
        user_id: Current user ID

    Returns:
        List of user's queue jobs with status
    """
    jobs = await QueueManagerDB.get_jobs_by_user(db, user_id)
    # Sort by created_at (newest first)
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    status = await QueueManagerDB.get_status(db, user_id=user_id)
    return QueueListResponse(jobs=jobs, status=status)


@router.post("/jobs", response_model=QueueJobResponse)
async def add_job(
    job_create: QueueJobCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> QueueJobResponse:
    """Add a new job to the upload queue.

    Args:
        job_create: Job creation request
        background_tasks: FastAPI background tasks
        db: Database session
        user_id: Current user ID

    Returns:
        Created job
    """
    job = await QueueManagerDB.add_job(db, job_create, user_id)

    # Ensure worker is running
    worker = get_queue_worker()
    if not worker.is_running():
        background_tasks.add_task(_start_worker)

    return QueueJobResponse(job=job, message="Job added to queue")


@router.post("/jobs/bulk", response_model=BulkQueueResponse)
async def add_bulk_jobs(
    request: BulkQueueRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> BulkQueueResponse:
    """Add multiple jobs to the upload queue.

    Args:
        request: Bulk queue request with multiple files
        background_tasks: FastAPI background tasks
        db: Database session
        user_id: Current user ID

    Returns:
        Bulk operation response
    """
    jobs = []
    for file_job in request.files:
        job = await QueueManagerDB.add_job(db, file_job, user_id)
        jobs.append(job)

    # Ensure worker is running
    worker = get_queue_worker()
    if not worker.is_running():
        background_tasks.add_task(_start_worker)

    return BulkQueueResponse(
        added_count=len(jobs),
        jobs=jobs,
        message=f"Added {len(jobs)} job(s) to queue",
    )


@router.get("/jobs/{job_id}", response_model=QueueJobResponse)
async def get_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> QueueJobResponse:
    """Get a specific job by ID.

    Args:
        job_id: Job UUID
        db: Database session
        user_id: Current user ID

    Returns:
        Job details
        
    Raises:
        HTTPException: If job not found or doesn't belong to user
    """
    job = await QueueManagerDB.get_job(db, job_id)
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
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> QueueJobResponse:
    """Cancel a pending job.

    Args:
        job_id: Job UUID
        db: Database session
        user_id: Current user ID

    Returns:
        Cancelled job
        
    Raises:
        HTTPException: If job not found, doesn't belong to user, or cannot be cancelled
    """
    # Verify job belongs to user
    job = await QueueManagerDB.get_job(db, job_id)
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
    cancelled_job = await QueueManagerDB.cancel_job(db, job_id)
    if not cancelled_job:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job cannot be cancelled",
        )

    return QueueJobResponse(job=cancelled_job, message="Job cancelled")


@router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Delete a job from the queue.

    Args:
        job_id: Job UUID
        db: Database session
        user_id: Current user ID

    Returns:
        Success message
        
    Raises:
        HTTPException: If job not found, doesn't belong to user, or is active
    """
    job = await QueueManagerDB.get_job(db, job_id)
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

    await QueueManagerDB.delete_job(db, job_id)
    return {"message": "Job deleted"}


@router.post("/clear")
async def clear_completed(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Clear all completed, failed, and cancelled jobs for the current user.

    Args:
        db: Database session
        user_id: Current user ID

    Returns:
        Number of jobs cleared
    """
    count = await QueueManagerDB.clear_completed(db, user_id=user_id)
    return {"message": f"Cleared {count} job(s)", "cleared_count": count}


@router.post("/worker/start")
async def start_worker(background_tasks: BackgroundTasks) -> dict:
    """Manually start the queue worker.

    Args:
        background_tasks: FastAPI background tasks

    Returns:
        Status message
    """
    worker = get_queue_worker()
    if worker.is_running():
        return {"message": "Worker already running"}

    background_tasks.add_task(_start_worker)
    return {"message": "Worker starting"}


@router.post("/worker/stop")
async def stop_worker(background_tasks: BackgroundTasks) -> dict:
    """Stop the queue worker.

    Args:
        background_tasks: FastAPI background tasks

    Returns:
        Status message
    """
    worker = get_queue_worker()
    if not worker.is_running():
        return {"message": "Worker not running"}

    background_tasks.add_task(worker.stop)
    return {"message": "Worker stopping"}


async def _start_worker() -> None:
    """Start the queue worker (used as background task)."""
    worker = get_queue_worker()
    await worker.start()
