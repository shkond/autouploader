"""Queue database repository layer.

Provides database access abstraction for queue job operations.
This layer handles direct database operations while the Service layer handles business logic.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.protocols import QueueRepositoryProtocol
from app.models import QueueJobModel
from app.queue.schemas import JobStatus, QueueJob, QueueJobCreate, QueueStatus
from app.youtube.schemas import VideoMetadata

logger = logging.getLogger(__name__)


class QueueRepository(QueueRepositoryProtocol):
    """Repository for queue database operations.

    Implements QueueRepositoryProtocol to provide a clean abstraction
    over the database operations. All methods are instance methods
    that use the injected database session.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize Queue repository with database session.

        Args:
            db: SQLAlchemy async session
        """
        self._db = db

    @staticmethod
    def _model_to_schema(model: QueueJobModel) -> QueueJob:
        """Convert database model to Pydantic schema.

        Args:
            model: QueueJobModel instance

        Returns:
            QueueJob schema
        """
        import json

        metadata = None
        if model.metadata_json:
            try:
                metadata_dict = json.loads(model.metadata_json)
                metadata = VideoMetadata(**metadata_dict)
            except (json.JSONDecodeError, TypeError):
                pass

        return QueueJob(
            id=model.id,
            drive_file_id=model.drive_file_id,
            drive_file_name=model.drive_file_name,
            drive_md5_checksum=model.drive_md5_checksum,
            file_size=model.file_size,
            folder_path=model.folder_path,
            batch_id=model.batch_id,
            metadata=metadata,
            status=JobStatus(model.status),
            progress=model.progress or 0.0,
            message=model.message or "",
            video_id=model.video_id,
            video_url=model.video_url,
            error=model.error,
            retry_count=model.retry_count or 0,
            max_retries=model.max_retries or 3,
            created_at=model.created_at,
            updated_at=model.updated_at,
            user_id=model.user_id,
        )

    async def add_job(
        self,
        job_create: QueueJobCreate,
        user_id: str,
    ) -> QueueJob:
        """Add a new job to the queue.

        Args:
            job_create: Job creation request
            user_id: User ID who created this job

        Returns:
            Created QueueJob
        """
        import json
        from uuid import uuid4

        metadata_json = None
        if job_create.metadata:
            metadata_json = json.dumps(job_create.metadata.model_dump())

        model = QueueJobModel(
            id=str(uuid4()),
            drive_file_id=job_create.drive_file_id,
            drive_file_name=job_create.drive_file_name,
            drive_md5_checksum=job_create.drive_md5_checksum,
            file_size=job_create.file_size,
            folder_path=job_create.folder_path,
            batch_id=job_create.batch_id,
            metadata_json=metadata_json,
            status=JobStatus.PENDING.value,
            progress=0.0,
            message="Queued for upload",
            user_id=user_id,
        )

        self._db.add(model)
        await self._db.flush()
        await self._db.refresh(model)

        logger.info(f"Added job {model.id} for file {job_create.drive_file_name}")
        return self._model_to_schema(model)

    async def get_job(self, job_id: UUID) -> QueueJob | None:
        """Get a job by ID.

        Args:
            job_id: Job UUID

        Returns:
            QueueJob or None if not found
        """
        result = await self._db.execute(
            select(QueueJobModel).where(QueueJobModel.id == job_id)
        )
        model = result.scalars().first()
        return self._model_to_schema(model) if model else None

    async def update_job(
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
        result = await self._db.execute(
            select(QueueJobModel).where(QueueJobModel.id == job_id)
        )
        model = result.scalars().first()

        if not model:
            return None

        if status is not None:
            model.status = status.value
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

        model.updated_at = datetime.now(UTC)
        await self._db.flush()
        await self._db.refresh(model)

        return self._model_to_schema(model)

    async def cancel_job(self, job_id: UUID) -> QueueJob | None:
        """Cancel a pending or downloading job.

        Args:
            job_id: Job UUID

        Returns:
            Cancelled QueueJob or None if not found or not cancellable
        """
        result = await self._db.execute(
            select(QueueJobModel).where(QueueJobModel.id == job_id)
        )
        model = result.scalars().first()

        if not model:
            return None

        cancellable_statuses = [JobStatus.PENDING.value, JobStatus.DOWNLOADING.value]
        if model.status not in cancellable_statuses:
            return None

        model.status = JobStatus.CANCELLED.value
        model.message = "Cancelled by user"
        model.updated_at = datetime.now(UTC)

        await self._db.flush()
        await self._db.refresh(model)

        logger.info(f"Cancelled job {job_id}")
        return self._model_to_schema(model)

    async def delete_job(self, job_id: UUID) -> bool:
        """Delete a job from the queue.

        Args:
            job_id: Job UUID

        Returns:
            True if deleted, False if not found
        """
        result = await self._db.execute(
            delete(QueueJobModel).where(QueueJobModel.id == job_id)
        )
        return result.rowcount > 0

    async def get_all_jobs(self) -> list[QueueJob]:
        """Get all jobs in the queue.

        Returns:
            List of all QueueJobs
        """
        result = await self._db.execute(
            select(QueueJobModel).order_by(QueueJobModel.created_at.desc())
        )
        models = result.scalars().all()
        return [self._model_to_schema(m) for m in models]

    async def get_jobs_by_user(self, user_id: str) -> list[QueueJob]:
        """Get all jobs for a specific user.

        Args:
            user_id: User identifier

        Returns:
            List of QueueJobs belonging to the user
        """
        result = await self._db.execute(
            select(QueueJobModel)
            .where(QueueJobModel.user_id == user_id)
            .order_by(QueueJobModel.created_at.desc())
        )
        models = result.scalars().all()
        return [self._model_to_schema(m) for m in models]

    async def get_pending_jobs(self) -> list[QueueJob]:
        """Get all pending jobs.

        Returns:
            List of pending QueueJobs
        """
        result = await self._db.execute(
            select(QueueJobModel)
            .where(QueueJobModel.status == JobStatus.PENDING.value)
            .order_by(QueueJobModel.created_at.asc())
        )
        models = result.scalars().all()
        return [self._model_to_schema(m) for m in models]

    async def get_next_pending_job(self) -> QueueJob | None:
        """Get the next pending job in queue order (FIFO).

        Returns:
            Next pending QueueJob or None
        """
        result = await self._db.execute(
            select(QueueJobModel)
            .where(QueueJobModel.status == JobStatus.PENDING.value)
            .order_by(QueueJobModel.created_at.asc())
            .limit(1)
        )
        model = result.scalars().first()
        return self._model_to_schema(model) if model else None

    async def get_active_jobs(self) -> list[QueueJob]:
        """Get all active (downloading/uploading) jobs.

        Returns:
            List of active QueueJobs
        """
        active_statuses = [JobStatus.DOWNLOADING.value, JobStatus.UPLOADING.value]
        result = await self._db.execute(
            select(QueueJobModel)
            .where(QueueJobModel.status.in_(active_statuses))
            .order_by(QueueJobModel.created_at.asc())
        )
        models = result.scalars().all()
        return [self._model_to_schema(m) for m in models]

    async def get_status(self, user_id: str | None = None) -> QueueStatus:
        """Get overall queue status, optionally filtered by user.

        Uses database aggregation for efficiency instead of loading all jobs.

        Args:
            user_id: Optional user ID to filter by

        Returns:
            QueueStatus summary
        """
        base_query = select(
            QueueJobModel.status,
            func.count(QueueJobModel.id).label("count"),
        )

        if user_id:
            base_query = base_query.where(QueueJobModel.user_id == user_id)

        base_query = base_query.group_by(QueueJobModel.status)

        result = await self._db.execute(base_query)
        status_counts = {row.status: row.count for row in result}

        pending = status_counts.get(JobStatus.PENDING.value, 0)
        downloading = status_counts.get(JobStatus.DOWNLOADING.value, 0)
        uploading = status_counts.get(JobStatus.UPLOADING.value, 0)
        completed = status_counts.get(JobStatus.COMPLETED.value, 0)
        failed = status_counts.get(JobStatus.FAILED.value, 0)
        cancelled = status_counts.get(JobStatus.CANCELLED.value, 0)

        total = pending + downloading + uploading + completed + failed + cancelled
        active = downloading + uploading

        return QueueStatus(
            total_jobs=total,
            pending=pending,
            active=active,
            completed=completed,
            failed=failed,
            cancelled=cancelled,
            is_processing=active > 0,
        )

    async def clear_completed(self, user_id: str | None = None) -> int:
        """Clear all completed jobs from the queue.

        Args:
            user_id: Optional user ID to filter by

        Returns:
            Number of jobs cleared
        """
        query = delete(QueueJobModel).where(
            QueueJobModel.status == JobStatus.COMPLETED.value
        )

        if user_id:
            query = query.where(QueueJobModel.user_id == user_id)

        result = await self._db.execute(query)
        cleared_count = result.rowcount

        logger.info(f"Cleared {cleared_count} completed jobs")
        return cleared_count

    async def is_file_id_in_queue(self, drive_file_id: str) -> bool:
        """Check if a file ID is already in the queue (pending or active).

        Args:
            drive_file_id: Google Drive file ID

        Returns:
            True if file is already in queue
        """
        active_statuses = [
            JobStatus.PENDING.value,
            JobStatus.DOWNLOADING.value,
            JobStatus.UPLOADING.value,
        ]

        result = await self._db.execute(
            select(func.count(QueueJobModel.id))
            .where(QueueJobModel.drive_file_id == drive_file_id)
            .where(QueueJobModel.status.in_(active_statuses))
        )

        count = result.scalar()
        return count > 0 if count else False

    async def is_md5_in_queue(self, md5_checksum: str) -> bool:
        """Check if a file with given MD5 is already in the queue.

        Args:
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

        result = await self._db.execute(
            select(func.count(QueueJobModel.id))
            .where(QueueJobModel.drive_md5_checksum == md5_checksum)
            .where(QueueJobModel.status.in_(active_statuses))
        )

        count = result.scalar()
        return count > 0 if count else False

    async def get_jobs_for_batch(self, batch_id: str) -> list[QueueJob]:
        """Get all jobs for a specific batch.

        Args:
            batch_id: Batch identifier

        Returns:
            List of QueueJobs in the batch
        """
        result = await self._db.execute(
            select(QueueJobModel)
            .where(QueueJobModel.batch_id == batch_id)
            .order_by(QueueJobModel.created_at.asc())
        )
        models = result.scalars().all()
        return [self._model_to_schema(m) for m in models]

    async def increment_retry_count(self, job_id: UUID) -> QueueJob | None:
        """Increment retry count for a job.

        Args:
            job_id: Job UUID

        Returns:
            Updated QueueJob or None if not found
        """
        result = await self._db.execute(
            select(QueueJobModel).where(QueueJobModel.id == job_id)
        )
        model = result.scalars().first()

        if not model:
            return None

        model.retry_count = (model.retry_count or 0) + 1
        model.updated_at = datetime.now(UTC)

        await self._db.flush()
        await self._db.refresh(model)

        return self._model_to_schema(model)
