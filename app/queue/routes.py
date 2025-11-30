"""Queue management routes."""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.queue.manager import get_queue_manager
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


@router.get("/status", response_model=QueueStatus)
async def get_queue_status() -> QueueStatus:
    """Get overall queue status.

    Returns:
        Queue status summary
    """
    manager = get_queue_manager()
    return manager.get_status()


@router.get("/jobs", response_model=QueueListResponse)
async def list_jobs() -> QueueListResponse:
    """List all jobs in the queue.

    Returns:
        List of all queue jobs with status
    """
    manager = get_queue_manager()
    jobs = manager.get_all_jobs()
    # Sort by created_at (newest first)
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    return QueueListResponse(jobs=jobs, status=manager.get_status())


@router.post("/jobs", response_model=QueueJobResponse)
async def add_job(
    job_create: QueueJobCreate, background_tasks: BackgroundTasks
) -> QueueJobResponse:
    """Add a new job to the upload queue.

    Args:
        job_create: Job creation request
        background_tasks: FastAPI background tasks

    Returns:
        Created job
    """
    manager = get_queue_manager()
    job = manager.add_job(job_create)

    # Ensure worker is running
    worker = get_queue_worker()
    if not worker.is_running():
        background_tasks.add_task(_start_worker)

    return QueueJobResponse(job=job, message="Job added to queue")


@router.post("/jobs/bulk", response_model=BulkQueueResponse)
async def add_bulk_jobs(
    request: BulkQueueRequest, background_tasks: BackgroundTasks
) -> BulkQueueResponse:
    """Add multiple jobs to the upload queue.

    Args:
        request: Bulk queue request with multiple files
        background_tasks: FastAPI background tasks

    Returns:
        Bulk operation response
    """
    manager = get_queue_manager()
    jobs = []
    for file_job in request.files:
        job = manager.add_job(file_job)
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
async def get_job(job_id: UUID) -> QueueJobResponse:
    """Get a specific job by ID.

    Args:
        job_id: Job UUID

    Returns:
        Job details
    """
    manager = get_queue_manager()
    job = manager.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    return QueueJobResponse(job=job)


@router.post("/jobs/{job_id}/cancel", response_model=QueueJobResponse)
async def cancel_job(job_id: UUID) -> QueueJobResponse:
    """Cancel a pending job.

    Args:
        job_id: Job UUID

    Returns:
        Cancelled job
    """
    manager = get_queue_manager()
    job = manager.cancel_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job not found or cannot be cancelled",
        )
    return QueueJobResponse(job=job, message="Job cancelled")


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: UUID) -> dict:
    """Delete a job from the queue.

    Args:
        job_id: Job UUID

    Returns:
        Success message
    """
    manager = get_queue_manager()
    job = manager.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    if job.status in (JobStatus.DOWNLOADING, JobStatus.UPLOADING):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete an active job. Cancel it first.",
        )

    manager.delete_job(job_id)
    return {"message": "Job deleted"}


@router.post("/clear")
async def clear_completed() -> dict:
    """Clear all completed, failed, and cancelled jobs.

    Returns:
        Number of jobs cleared
    """
    manager = get_queue_manager()
    count = manager.clear_completed()
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
