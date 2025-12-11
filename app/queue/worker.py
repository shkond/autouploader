"""Background worker for processing upload queue."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from app.auth.oauth import get_oauth_service
from app.config import get_settings
from app.queue.schemas import JobStatus, QueueJob
from app.youtube.quota import get_quota_tracker
from app.youtube.schemas import UploadProgress
from app.youtube.service import YouTubeService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Type alias for skip result dictionary
SkipResult = dict[str, Any]


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
        from app.database import get_db_context
        from app.queue.repositories import QueueRepository

        # Maximum wait time when quota exhausted (1 hour)
        max_quota_wait_seconds = 3600

        while self._running:
            try:
                # Check quota before attempting to process any jobs
                quota_tracker = get_quota_tracker()
                if not quota_tracker.can_perform("videos.insert"):
                    remaining_quota = quota_tracker.get_remaining_quota()
                    logger.warning(
                        "Quota exhausted (remaining=%d). "
                        "Waiting %d seconds before checking again.",
                        remaining_quota,
                        max_quota_wait_seconds,
                    )
                    await asyncio.sleep(max_quota_wait_seconds)
                    continue

                async with get_db_context() as db:
                    repo = QueueRepository(db)
                    # Check for pending jobs
                    active_jobs = await repo.get_active_jobs()
                    if len(active_jobs) >= self.settings.max_concurrent_uploads:
                        await asyncio.sleep(5)
                        continue

                    next_job = await repo.get_next_pending_job()
                    if not next_job:
                        await asyncio.sleep(5)
                        continue

                    # Process the job
                    await self._process_job(next_job.id)

            except Exception:
                logger.exception("Error in worker loop")
                await asyncio.sleep(5)

    async def _process_job(self, job_id: Any) -> None:
        """Process a single upload job with a single DB session.

        Args:
            job_id: Job UUID to process
        """
        from app.database import get_db_context
        from app.drive.services import DriveService
        from app.queue.repositories import QueueRepository

        async with get_db_context() as db:
            repo = QueueRepository(db)
            job = await repo.get_job(job_id)
            if not job:
                return

            logger.info("Processing job %s: %s", job.id, job.drive_file_name)

            try:
                # Get YouTube service for the job user
                oauth_service = get_oauth_service()
                credentials = await oauth_service.get_credentials(job.user_id)
                if not credentials:
                    raise Exception("User not authenticated with Google")
                youtube_service = YouTubeService(credentials)

                # Pre-upload check: verify if video was already uploaded
                skip_result = await self._pre_upload_check(job, youtube_service, db)
                if skip_result["skip"]:
                    await repo.update_job(
                        job_id,
                        status=JobStatus.COMPLETED,
                        progress=100,
                        message=skip_result["reason"],
                        video_id=skip_result.get("video_id"),
                        video_url=skip_result.get("video_url"),
                    )
                    await db.commit()  # Explicit commit for UI update
                    logger.info(
                        "Job %s skipped: %s", job.id, skip_result["reason"]
                    )
                    return

                # Pre-upload check: validate file size from Drive metadata
                drive_service = DriveService(credentials)
                file_info = await drive_service.get_file_metadata(job.drive_file_id)
                file_size = int(file_info.get("size", 0))

                settings = get_settings()
                if file_size > settings.max_file_size:
                    size_gb = file_size / (1024 ** 3)
                    max_gb = settings.max_file_size / (1024 ** 3)
                    error_msg = f"File too large ({size_gb:.2f}GB > {max_gb:.0f}GB max)"
                    await repo.update_job(
                        job_id,
                        status=JobStatus.FAILED,
                        message=error_msg,
                        error=error_msg,
                    )
                    await db.commit()  # Explicit commit for UI update
                    logger.error("Job %s failed: %s", job.id, error_msg)
                    return

                # Update status to downloading
                await repo.update_job(
                    job_id,
                    status=JobStatus.DOWNLOADING,
                    message="Starting download from Google Drive...",
                )
                await db.commit()  # Explicit commit for UI update

                # Create progress callback that uses the shared session
                async def progress_callback(progress: UploadProgress) -> None:
                    status = JobStatus.DOWNLOADING
                    if progress.status == "uploading":
                        status = JobStatus.UPLOADING

                    await repo.update_job(
                        job_id,
                        status=status,
                        progress=progress.progress,
                        message=progress.message,
                    )
                    await db.commit()  # Explicit commit for real-time progress

                # Upload from Drive to YouTube with retry logic (using async version)
                result = await youtube_service.upload_from_drive_with_retry_async(
                    drive_file_id=job.drive_file_id,
                    metadata=job.metadata,
                    progress_callback=progress_callback,
                    drive_credentials=credentials,
                )

                if result.success:
                    await repo.update_job(
                        job_id,
                        status=JobStatus.COMPLETED,
                        progress=100,
                        message="Upload completed successfully",
                        video_id=result.video_id,
                        video_url=result.video_url,
                    )
                    await db.commit()  # Explicit commit for UI update
                    logger.info("Job %s completed: video_id=%s", job.id, result.video_id)

                    # Save upload history to database (using shared session)
                    await self._save_upload_history(
                        job=job,
                        video_id=result.video_id or "",
                        video_url=result.video_url or "",
                        db=db,
                    )
                else:
                    await repo.update_job(
                        job_id,
                        status=JobStatus.FAILED,
                        message=result.message,
                        error=result.error,
                    )
                    await db.commit()  # Explicit commit for UI update
                    logger.error("Job %s failed: %s", job.id, result.error)

            except Exception as e:
                logger.exception("Job %s failed with exception", job_id)
                await db.rollback()  # Rollback any pending changes
                await repo.update_job(
                    job_id,
                    status=JobStatus.FAILED,
                    message="Upload failed",
                    error=str(e),
                )
                await db.commit()  # Commit the error status

    @staticmethod
    async def _pre_upload_check(
        job: "QueueJob",
        youtube_service: "YouTubeService",
        db: "AsyncSession",
    ) -> "SkipResult":
        """Check if upload should be skipped (already uploaded).

        Args:
            job: Queue job to check
            youtube_service: YouTube service instance
            db: Database session (injected from caller)

        Returns:
            Dict with skip (bool), reason (str), and optionally video_id/video_url
        """
        from sqlalchemy import select

        from app.models import UploadHistory

        if not job.drive_md5_checksum:
            return {"skip": False}

        # Check if this file was already uploaded (by MD5)
        result = await db.execute(
            select(UploadHistory).where(
                UploadHistory.drive_md5_checksum == job.drive_md5_checksum
            )
        )
        history = result.scalars().first()

        if not history or not history.youtube_video_id:
            return {"skip": False}

        # Check if we verified recently (within 24 hours)
        now = datetime.now(UTC)
        if history.last_verified_at:
            time_since_verify = now - history.last_verified_at
            if time_since_verify < timedelta(hours=24):
                logger.info(
                    "Video %s verified within 24h, skipping",
                    history.youtube_video_id,
                )
                # Calculate hours ago using total_seconds() to include days
                hours_ago = int(time_since_verify.total_seconds() // 3600)
                return {
                    "skip": True,
                    "reason": f"Already uploaded (verified {hours_ago}h ago)",
                    "video_id": history.youtube_video_id,
                    "video_url": history.youtube_video_url,
                }

        # Verify video still exists on YouTube (costs 1 quota unit)
        exists = youtube_service.check_video_exists_on_youtube(
            history.youtube_video_id
        )

        if exists:
            # Update last_verified_at
            history.last_verified_at = now
            await db.commit()

            return {
                "skip": True,
                "reason": "Already uploaded and verified on YouTube",
                "video_id": history.youtube_video_id,
                "video_url": history.youtube_video_url,
            }

        return {"skip": False}


    def is_running(self) -> bool:
        """Check if the worker is running.

        Returns:
            True if running
        """
        return self._running

    async def process_batch(self, max_jobs: int = 0) -> int:
        """Process pending jobs until queue is empty (for Scheduler).

        This method is designed for Heroku Scheduler or cron-like execution.
        It processes all pending jobs and then exits, rather than running
        continuously like the main worker loop.

        Args:
            max_jobs: Maximum number of jobs to process (0 = unlimited)

        Returns:
            Number of jobs processed
        """
        from app.database import get_db_context
        from app.queue.repositories import QueueRepository

        processed = 0
        logger.info("Starting batch processing...")

        try:
            # Check quota before starting
            quota_tracker = get_quota_tracker()
            if not quota_tracker.can_perform("videos.insert"):
                remaining_quota = quota_tracker.get_remaining_quota()
                logger.warning(
                    "Quota exhausted (remaining=%d). Skipping batch.",
                    remaining_quota,
                )
                return 0

            while True:
                # Check max jobs limit
                if max_jobs > 0 and processed >= max_jobs:
                    logger.info("Reached max jobs limit (%d)", max_jobs)
                    break

                # Get next pending job
                async with get_db_context() as db:
                    repo = QueueRepository(db)
                    next_job = await repo.get_next_pending_job()

                    if not next_job:
                        logger.info("No more pending jobs.")
                        break

                # Process the job
                await self._process_job(next_job.id)
                processed += 1

                # Re-check quota after each job
                if not quota_tracker.can_perform("videos.insert"):
                    logger.warning("Quota exhausted during batch processing.")
                    break

        except Exception:
            logger.exception("Error during batch processing")

        logger.info("Batch complete. Processed %d jobs.", processed)
        return processed

    @staticmethod
    async def _save_upload_history(
        job: "QueueJob",
        video_id: str,
        video_url: str,
        db: "AsyncSession",
    ) -> None:
        """Save upload history to database.

        Args:
            job: Completed queue job
            video_id: YouTube video ID
            video_url: YouTube video URL
            db: Database session (injected from caller)
        """
        from app.models import UploadHistory

        history = UploadHistory(
            drive_file_id=job.drive_file_id,
            drive_file_name=job.drive_file_name,
            drive_md5_checksum=job.drive_md5_checksum or "",
            youtube_video_id=video_id,
            youtube_video_url=video_url,
            folder_path=job.folder_path or "",
            status="completed",
            uploaded_at=datetime.now(UTC),
        )
        db.add(history)
        await db.commit()
        logger.info(
            "Saved upload history: %s -> %s",
            job.drive_file_name,
            video_id,
        )



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


async def run_standalone_worker() -> None:
    """Run the worker as a standalone process.

    This is the entry point when running the worker separately from the web process.
    Handles graceful shutdown on SIGINT and SIGTERM.
    """
    import signal
    import sys

    from app.database import close_db, init_db

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("Starting standalone worker process...")

    # Initialize database
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized")

    worker = get_queue_worker()

    # Set up signal handlers for graceful shutdown
    shutdown_event = asyncio.Event()

    def signal_handler(sig: int, _frame: Any) -> None:
        """Handle shutdown signals (SIGTERM, SIGINT)."""
        logger.info("Received signal %s, initiating graceful shutdown...", sig)
        shutdown_event.set()

    # Register signal handlers
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        # Start worker
        await worker.start()
        logger.info("Worker started, waiting for jobs...")

        # Wait for shutdown signal
        await shutdown_event.wait()

    except asyncio.CancelledError:
        logger.info("Worker cancelled")
    finally:
        # Graceful shutdown
        logger.info("Stopping worker...")
        await worker.stop()

        # Close database connections
        logger.info("Closing database connections...")
        await close_db()
        logger.info("Worker shutdown complete")


if __name__ == "__main__":
    """Entry point for standalone worker execution.

    Usage: python -m app.queue.worker
    """
    asyncio.run(run_standalone_worker())

