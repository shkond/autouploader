"""Background worker for processing upload queue."""

import asyncio
import logging
from typing import Any

from app.config import get_settings
from app.queue.manager import get_queue_manager
from app.queue.schemas import JobStatus
from app.youtube.schemas import UploadProgress
from app.youtube.service import get_youtube_service

logger = logging.getLogger(__name__)


class QueueWorker:
    """Background worker for processing upload jobs."""

    def __init__(self) -> None:
        """Initialize queue worker."""
        self.settings = get_settings()
        self._running = False
        self._task: asyncio.Task[Any] | None = None

    async def start(self) -> None:
        """Start the background worker."""
        if self._running:
            logger.warning("Worker already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("Queue worker started")

    async def stop(self) -> None:
        """Stop the background worker."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Queue worker stopped")

    async def _process_loop(self) -> None:
        """Main processing loop."""
        queue_manager = get_queue_manager()

        while self._running:
            try:
                # Check for pending jobs
                active_jobs = queue_manager.get_active_jobs()
                if len(active_jobs) >= self.settings.max_concurrent_uploads:
                    await asyncio.sleep(5)
                    continue

                next_job = queue_manager.get_next_pending_job()
                if not next_job:
                    queue_manager.set_processing(False)
                    await asyncio.sleep(5)
                    continue

                queue_manager.set_processing(True)

                # Process the job
                await self._process_job(next_job.id)

            except Exception:
                logger.exception("Error in worker loop")
                await asyncio.sleep(5)

    async def _process_job(self, job_id: Any) -> None:
        """Process a single upload job.

        Args:
            job_id: Job UUID to process
        """
        queue_manager = get_queue_manager()
        job = queue_manager.get_job(job_id)
        if not job:
            return

        logger.info("Processing job %s: %s", job.id, job.drive_file_name)

        try:
            # Update status to downloading
            queue_manager.update_job(
                job_id,
                status=JobStatus.DOWNLOADING,
                message="Starting download from Google Drive...",
            )

            # Get YouTube service
            youtube_service = get_youtube_service()

            # Create progress callback
            def progress_callback(progress: UploadProgress) -> None:
                status = JobStatus.DOWNLOADING
                if progress.status == "uploading":
                    status = JobStatus.UPLOADING
                queue_manager.update_job(
                    job_id,
                    status=status,
                    progress=progress.progress,
                    message=progress.message,
                )

            # Upload from Drive to YouTube
            result = youtube_service.upload_from_drive(
                drive_file_id=job.drive_file_id,
                metadata=job.metadata,
                progress_callback=progress_callback,
            )

            if result.success:
                queue_manager.update_job(
                    job_id,
                    status=JobStatus.COMPLETED,
                    progress=100,
                    message="Upload completed successfully",
                    video_id=result.video_id,
                    video_url=result.video_url,
                )
                logger.info("Job %s completed: video_id=%s", job.id, result.video_id)
            else:
                queue_manager.update_job(
                    job_id,
                    status=JobStatus.FAILED,
                    message=result.message,
                    error=result.error,
                )
                logger.error("Job %s failed: %s", job.id, result.error)

        except Exception as e:
            logger.exception("Job %s failed with exception", job_id)
            queue_manager.update_job(
                job_id,
                status=JobStatus.FAILED,
                message="Upload failed",
                error=str(e),
            )

    def is_running(self) -> bool:
        """Check if the worker is running.

        Returns:
            True if running
        """
        return self._running


# Singleton instance
_queue_worker: QueueWorker | None = None


def get_queue_worker() -> QueueWorker:
    """Get or create queue worker singleton.

    Returns:
        QueueWorker instance
    """
    global _queue_worker
    if _queue_worker is None:
        _queue_worker = QueueWorker()
    return _queue_worker
