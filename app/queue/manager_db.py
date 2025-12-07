"""Database-backed upload queue manager.

This replaces the in-memory QueueManager with a persistent database implementation.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import QueueJobModel
from app.queue.schemas import JobStatus, QueueJob, QueueJobCreate, QueueStatus
from app.youtube.schemas import VideoMetadata

logger = logging.getLogger(__name__)


class QueueManagerDB:
    """Database-backed queue manager for persistent storage.
    
    This implementation uses QueueJobModel for database persistence,
    enabling multi-user support and data survival across server restarts.
    """

    @staticmethod
    def _model_to_schema(model: QueueJobModel) -> QueueJob:
        """Convert database model to Pydantic schema.
        
        Args:
            model: QueueJobModel instance
            
        Returns:
            QueueJob schema
        """
        metadata = VideoMetadata.model_validate_json(model.metadata_json)

        return QueueJob(
            id=UUID(model.id) if isinstance(model.id, str) else model.id,
            user_id=model.user_id,
            drive_file_id=model.drive_file_id,
            drive_file_name=model.drive_file_name,
            drive_md5_checksum=model.drive_md5_checksum,
            folder_path=model.folder_path,
            batch_id=model.batch_id,
            metadata=metadata,
            status=JobStatus(model.status),
            progress=model.progress,
            message=model.message,
            video_id=model.video_id,
            video_url=model.video_url,
            error=model.error,
            created_at=model.created_at,
            started_at=model.started_at,
            completed_at=model.completed_at,
            retry_count=model.retry_count,
            max_retries=model.max_retries,
        )

    @staticmethod
    async def add_job(
        db: AsyncSession, job_create: QueueJobCreate, user_id: str
    ) -> QueueJob:
        """Add a new job to the queue.
        
        Args:
            db: Database session
            job_create: Job creation request
            user_id: User ID who created this job
            
        Returns:
            Created QueueJob
        """
        from uuid import uuid4

        job_id = str(uuid4())

        model = QueueJobModel(
            id=job_id,
            user_id=user_id,
            drive_file_id=job_create.drive_file_id,
            drive_file_name=job_create.drive_file_name,
            drive_md5_checksum=job_create.drive_md5_checksum,
            folder_path=job_create.folder_path,
            batch_id=job_create.batch_id,
            metadata_json=job_create.metadata.model_dump_json(),
            status=JobStatus.PENDING.value,
            progress=0.0,
            message="",
            retry_count=0,
            max_retries=3,
            created_at=datetime.now(UTC),
        )

        db.add(model)
        await db.commit()
        await db.refresh(model)

        logger.info(
            "Added job %s for file %s (user: %s)",
            job_id,
            job_create.drive_file_name,
            user_id,
        )

        return QueueManagerDB._model_to_schema(model)

    @staticmethod
    async def get_job(db: AsyncSession, job_id: UUID) -> QueueJob | None:
        """Get a job by ID.
        
        Args:
            db: Database session
            job_id: Job UUID
            
        Returns:
            QueueJob or None if not found
        """
        result = await db.execute(
            select(QueueJobModel).where(QueueJobModel.id == str(job_id))
        )
        model = result.scalars().first()

        if not model:
            return None

        return QueueManagerDB._model_to_schema(model)

    @staticmethod
    async def update_job(
        db: AsyncSession,
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
            db: Database session
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
        result = await db.execute(
            select(QueueJobModel).where(QueueJobModel.id == str(job_id))
        )
        model = result.scalars().first()

        if not model:
            return None

        # Update fields
        if status is not None:
            model.status = status.value
            if status in (JobStatus.DOWNLOADING, JobStatus.UPLOADING):
                if model.started_at is None:
                    model.started_at = datetime.now(UTC)
            elif status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                model.completed_at = datetime.now(UTC)

        if progress is not None:
            model.progress = progress
        if message is not None:
            model.message = message
        if video_id is not None:
            model.video_id = video_id
        if video_url is not None:
            model.video_url = video_url
        if error is not None:
            model.error = error

        await db.commit()
        await db.refresh(model)

        return QueueManagerDB._model_to_schema(model)

    @staticmethod
    async def cancel_job(db: AsyncSession, job_id: UUID) -> QueueJob | None:
        """Cancel a pending or downloading job.
        
        Args:
            db: Database session
            job_id: Job UUID
            
        Returns:
            Cancelled QueueJob or None if not found or not cancellable
        """
        result = await db.execute(
            select(QueueJobModel).where(QueueJobModel.id == str(job_id))
        )
        model = result.scalars().first()

        if not model:
            return None

        # Only allow cancelling jobs that haven't started uploading
        if model.status not in (JobStatus.PENDING.value, JobStatus.DOWNLOADING.value):
            return None

        model.status = JobStatus.CANCELLED.value
        model.completed_at = datetime.now(UTC)
        model.message = "Cancelled by user"

        await db.commit()
        await db.refresh(model)

        return QueueManagerDB._model_to_schema(model)

    @staticmethod
    async def delete_job(db: AsyncSession, job_id: UUID) -> bool:
        """Delete a job from the queue.
        
        Args:
            db: Database session
            job_id: Job UUID
            
        Returns:
            True if deleted, False if not found
        """
        result = await db.execute(
            delete(QueueJobModel).where(QueueJobModel.id == str(job_id))
        )
        await db.commit()

        return result.rowcount > 0

    @staticmethod
    async def get_all_jobs(db: AsyncSession) -> list[QueueJob]:
        """Get all jobs in the queue.
        
        Args:
            db: Database session
            
        Returns:
            List of all QueueJobs
        """
        result = await db.execute(select(QueueJobModel))
        models = result.scalars().all()

        return [QueueManagerDB._model_to_schema(m) for m in models]

    @staticmethod
    async def get_jobs_by_user(db: AsyncSession, user_id: str) -> list[QueueJob]:
        """Get all jobs for a specific user.
        
        Args:
            db: Database session
            user_id: User identifier
            
        Returns:
            List of QueueJobs belonging to the user
        """
        result = await db.execute(
            select(QueueJobModel).where(QueueJobModel.user_id == user_id)
        )
        models = result.scalars().all()

        return [QueueManagerDB._model_to_schema(m) for m in models]

    @staticmethod
    async def get_pending_jobs(db: AsyncSession) -> list[QueueJob]:
        """Get all pending jobs.
        
        Args:
            db: Database session
            
        Returns:
            List of pending QueueJobs
        """
        result = await db.execute(
            select(QueueJobModel)
            .where(QueueJobModel.status == JobStatus.PENDING.value)
            .order_by(QueueJobModel.created_at.asc())
        )
        models = result.scalars().all()

        return [QueueManagerDB._model_to_schema(m) for m in models]

    @staticmethod
    async def get_next_pending_job(db: AsyncSession) -> QueueJob | None:
        """Get the next pending job in queue order (FIFO).
        
        Args:
            db: Database session
            
        Returns:
            Next pending QueueJob or None
        """
        result = await db.execute(
            select(QueueJobModel)
            .where(QueueJobModel.status == JobStatus.PENDING.value)
            .order_by(QueueJobModel.created_at.asc())
            .limit(1)
        )
        model = result.scalars().first()

        if not model:
            return None

        return QueueManagerDB._model_to_schema(model)

    @staticmethod
    async def get_active_jobs(db: AsyncSession) -> list[QueueJob]:
        """Get all active (downloading/uploading) jobs.
        
        Args:
            db: Database session
            
        Returns:
            List of active QueueJobs
        """
        active_statuses = [JobStatus.DOWNLOADING.value, JobStatus.UPLOADING.value]

        result = await db.execute(
            select(QueueJobModel).where(QueueJobModel.status.in_(active_statuses))
        )
        models = result.scalars().all()

        return [QueueManagerDB._model_to_schema(m) for m in models]

    @staticmethod
    async def get_status(
        db: AsyncSession, user_id: str | None = None
    ) -> QueueStatus:
        """Get overall queue status, optionally filtered by user.
        
        Uses database aggregation for efficiency instead of loading all jobs.
        
        Args:
            db: Database session
            user_id: Optional user ID to filter by
            
        Returns:
            QueueStatus summary
        """
        from sqlalchemy import case

        # Build base query with conditional aggregation
        query = select(
            func.count().label("total"),
            func.sum(
                case((QueueJobModel.status == JobStatus.PENDING.value, 1), else_=0)
            ).label("pending"),
            func.sum(
                case(
                    (
                        QueueJobModel.status.in_(
                            [JobStatus.DOWNLOADING.value, JobStatus.UPLOADING.value]
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("active"),
            func.sum(
                case((QueueJobModel.status == JobStatus.COMPLETED.value, 1), else_=0)
            ).label("completed"),
            func.sum(
                case((QueueJobModel.status == JobStatus.FAILED.value, 1), else_=0)
            ).label("failed"),
        )

        if user_id:
            query = query.where(QueueJobModel.user_id == user_id)

        result = await db.execute(query)
        row = result.first()

        return QueueStatus(
            total_jobs=row.total or 0,
            pending_jobs=row.pending or 0,
            active_jobs=row.active or 0,
            completed_jobs=row.completed or 0,
            failed_jobs=row.failed or 0,
            # Note: is_processing is hardcoded to False as worker state tracking
            # requires a separate heartbeat mechanism (future enhancement)
            is_processing=False,
        )

    @staticmethod
    async def clear_completed(
        db: AsyncSession, user_id: str | None = None
    ) -> int:
        """Clear all completed jobs from the queue.
        
        Args:
            db: Database session
            user_id: Optional user ID to filter by
            
        Returns:
            Number of jobs cleared
        """
        completed_statuses = [
            JobStatus.COMPLETED.value,
            JobStatus.FAILED.value,
            JobStatus.CANCELLED.value,
        ]

        query = delete(QueueJobModel).where(
            QueueJobModel.status.in_(completed_statuses)
        )

        if user_id:
            query = query.where(QueueJobModel.user_id == user_id)

        result = await db.execute(query)
        await db.commit()

        return result.rowcount

    @staticmethod
    async def is_file_id_in_queue(db: AsyncSession, drive_file_id: str) -> bool:
        """Check if a file ID is already in the queue (pending or active).
        
        Args:
            db: Database session
            drive_file_id: Google Drive file ID
            
        Returns:
            True if file is already in queue
        """
        active_statuses = [
            JobStatus.PENDING.value,
            JobStatus.DOWNLOADING.value,
            JobStatus.UPLOADING.value,
        ]

        result = await db.execute(
            select(func.count())
            .select_from(QueueJobModel)
            .where(
                QueueJobModel.drive_file_id == drive_file_id,
                QueueJobModel.status.in_(active_statuses),
            )
        )
        count = result.scalar()

        return count > 0

    @staticmethod
    async def is_md5_in_queue(db: AsyncSession, md5_checksum: str) -> bool:
        """Check if a file with given MD5 is already in the queue.
        
        Args:
            db: Database session
            md5_checksum: MD5 checksum of the file
            
        Returns:
            True if file with same MD5 is in queue
        """
        if not md5_checksum:
            return False

        active_statuses = [
            JobStatus.PENDING.value,
            JobStatus.DOWNLOADING.value,
            JobStatus.UPLOADING.value,
        ]

        result = await db.execute(
            select(func.count())
            .select_from(QueueJobModel)
            .where(
                QueueJobModel.drive_md5_checksum == md5_checksum,
                QueueJobModel.status.in_(active_statuses),
            )
        )
        count = result.scalar()

        return count > 0

    @staticmethod
    async def get_jobs_by_batch(db: AsyncSession, batch_id: str) -> list[QueueJob]:
        """Get all jobs for a specific batch.
        
        Args:
            db: Database session
            batch_id: Batch ID
            
        Returns:
            List of jobs in the batch
        """
        result = await db.execute(
            select(QueueJobModel).where(QueueJobModel.batch_id == batch_id)
        )
        models = result.scalars().all()

        return [QueueManagerDB._model_to_schema(m) for m in models]
