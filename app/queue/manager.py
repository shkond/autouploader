"""Upload queue manager."""

import logging
from datetime import datetime
from uuid import UUID

from app.queue.schemas import JobStatus, QueueJob, QueueJobCreate, QueueStatus

logger = logging.getLogger(__name__)


class QueueManager:
    """Manages upload queue jobs in memory.

    For production, this should be replaced with a persistent store
    (Redis, PostgreSQL, etc.)
    """

    def __init__(self) -> None:
        """Initialize queue manager."""
        self._jobs: dict[UUID, QueueJob] = {}
        self._is_processing = False

    def add_job(self, job_create: QueueJobCreate, user_id: str = "") -> QueueJob:
        """Add a new job to the queue.

        Args:
            job_create: Job creation request
            user_id: User ID who created this job

        Returns:
            Created QueueJob
        """
        job = QueueJob(
            user_id=user_id,
            drive_file_id=job_create.drive_file_id,
            drive_file_name=job_create.drive_file_name,
            drive_md5_checksum=job_create.drive_md5_checksum,
            folder_path=job_create.folder_path,
            batch_id=job_create.batch_id,
            metadata=job_create.metadata,
            status=JobStatus.PENDING,
        )
        self._jobs[job.id] = job
        logger.info("Added job %s for file %s (user: %s)", job.id, job.drive_file_name, user_id)
        return job


    def get_job(self, job_id: UUID) -> QueueJob | None:
        """Get a job by ID.

        Args:
            job_id: Job UUID

        Returns:
            QueueJob or None if not found
        """
        return self._jobs.get(job_id)

    def update_job(
        self,
        job_id: UUID,
        status: JobStatus | None = None,
        progress: float | None = None,
        message: str | None = None,
        video_id: str | None = None,
        video_url: str | None = None,
        error: str | None = None,
    ) -> QueueJob | None:
        """Update a job's status and progress.

        Args:
            job_id: Job UUID
            status: New status (optional)
            progress: New progress (optional)
            message: Status message (optional)
            video_id: YouTube video ID (optional)
            video_url: YouTube video URL (optional)
            error: Error message (optional)

        Returns:
            Updated QueueJob or None if not found
        """
        job = self._jobs.get(job_id)
        if not job:
            return None

        if status is not None:
            job.status = status
            if status == JobStatus.DOWNLOADING or status == JobStatus.UPLOADING:
                if job.started_at is None:
                    job.started_at = datetime.now()
            elif status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                job.completed_at = datetime.now()

        if progress is not None:
            job.progress = progress
        if message is not None:
            job.message = message
        if video_id is not None:
            job.video_id = video_id
        if video_url is not None:
            job.video_url = video_url
        if error is not None:
            job.error = error

        return job

    def cancel_job(self, job_id: UUID) -> QueueJob | None:
        """Cancel a pending or downloading job.

        Note: Only PENDING and DOWNLOADING jobs can be cancelled.
        UPLOADING jobs cannot be cancelled as the YouTube upload may have
        already started and partial data may have been sent. To stop an
        uploading job, you would need to restart the worker.

        Args:
            job_id: Job UUID

        Returns:
            Cancelled QueueJob or None if not found or not cancellable
        """
        job = self._jobs.get(job_id)
        if not job:
            return None

        # Only allow cancelling jobs that haven't started uploading to YouTube
        if job.status not in (JobStatus.PENDING, JobStatus.DOWNLOADING):
            return None

        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.now()
        job.message = "Cancelled by user"
        return job

    def delete_job(self, job_id: UUID) -> bool:
        """Delete a job from the queue.

        Args:
            job_id: Job UUID

        Returns:
            True if deleted, False if not found
        """
        if job_id in self._jobs:
            del self._jobs[job_id]
            return True
        return False

    def get_all_jobs(self) -> list[QueueJob]:
        """Get all jobs in the queue.

        Returns:
            List of all QueueJobs
        """
        return list(self._jobs.values())

    def get_jobs_by_user(self, user_id: str) -> list[QueueJob]:
        """Get all jobs for a specific user.

        Args:
            user_id: User identifier

        Returns:
            List of QueueJobs belonging to the user
        """
        return [j for j in self._jobs.values() if j.user_id == user_id]

    def get_pending_jobs(self) -> list[QueueJob]:
        """Get all pending jobs.

        Returns:
            List of pending QueueJobs
        """
        return [j for j in self._jobs.values() if j.status == JobStatus.PENDING]

    def get_next_pending_job(self) -> QueueJob | None:
        """Get the next pending job in queue order.

        Returns:
            Next pending QueueJob or None
        """
        pending = self.get_pending_jobs()
        if not pending:
            return None
        # Sort by created_at to maintain FIFO order
        pending.sort(key=lambda j: j.created_at)
        return pending[0]

    def get_active_jobs(self) -> list[QueueJob]:
        """Get all active (downloading/uploading) jobs.

        Returns:
            List of active QueueJobs
        """
        active_statuses = {JobStatus.DOWNLOADING, JobStatus.UPLOADING}
        return [j for j in self._jobs.values() if j.status in active_statuses]

    def get_status(self) -> QueueStatus:
        """Get overall queue status.

        Returns:
            QueueStatus summary
        """
        jobs = list(self._jobs.values())
        return QueueStatus(
            total_jobs=len(jobs),
            pending_jobs=sum(1 for j in jobs if j.status == JobStatus.PENDING),
            active_jobs=sum(
                1
                for j in jobs
                if j.status in (JobStatus.DOWNLOADING, JobStatus.UPLOADING)
            ),
            completed_jobs=sum(1 for j in jobs if j.status == JobStatus.COMPLETED),
            failed_jobs=sum(1 for j in jobs if j.status == JobStatus.FAILED),
            is_processing=self._is_processing,
        )

    def set_processing(self, is_processing: bool) -> None:
        """Set the processing state.

        Args:
            is_processing: Whether the queue is being processed
        """
        self._is_processing = is_processing

    def clear_completed(self) -> int:
        """Clear all completed jobs from the queue.

        Returns:
            Number of jobs cleared
        """
        completed_ids = [
            job_id
            for job_id, job in self._jobs.items()
            if job.status
            in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)
        ]
        for job_id in completed_ids:
            del self._jobs[job_id]
        return len(completed_ids)

    def is_file_id_in_queue(self, drive_file_id: str) -> bool:
        """Check if a file ID is already in the queue (pending or active).

        Args:
            drive_file_id: Google Drive file ID

        Returns:
            True if file is already in queue
        """
        active_statuses = {JobStatus.PENDING, JobStatus.DOWNLOADING, JobStatus.UPLOADING}
        return any(
            job.drive_file_id == drive_file_id and job.status in active_statuses
            for job in self._jobs.values()
        )

    def is_md5_in_queue(self, md5_checksum: str) -> bool:
        """Check if a file with given MD5 is already in the queue.

        Args:
            md5_checksum: MD5 checksum of the file

        Returns:
            True if file with same MD5 is in queue
        """
        if not md5_checksum:
            return False
        active_statuses = {JobStatus.PENDING, JobStatus.DOWNLOADING, JobStatus.UPLOADING}
        return any(
            job.drive_md5_checksum == md5_checksum and job.status in active_statuses
            for job in self._jobs.values()
        )

    def get_jobs_by_batch(self, batch_id: str) -> list[QueueJob]:
        """Get all jobs for a specific batch.

        Args:
            batch_id: Batch ID

        Returns:
            List of jobs in the batch
        """
        return [job for job in self._jobs.values() if job.batch_id == batch_id]




# Singleton instance
_queue_manager: QueueManager | None = None


def get_queue_manager() -> QueueManager:
    """Get or create queue manager singleton.

    Returns:
        QueueManager instance
    """
    global _queue_manager
    if _queue_manager is None:
        _queue_manager = QueueManager()
    return _queue_manager
