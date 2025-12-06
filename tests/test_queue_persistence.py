"""Tests for persistent queue functionality.

Test categories:
2.1 キュー永続化テスト
2.2 キュー操作テスト
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.youtube.schemas import PrivacyStatus, VideoMetadata


def make_job_id() -> str:
    """Create a string job ID for SQLite compatibility."""
    return str(uuid4())


class TestQueuePersistence:
    """2.1 キュー永続化テスト"""

    @pytest.mark.asyncio
    async def test_queue_job_model_creation(self, test_session: AsyncSession):
        """Test QueueJob model can be created and saved to database."""
        from app.models import QueueJobModel

        job_id = make_job_id()
        metadata = VideoMetadata(
            title="Test Video",
            description="Test description",
            privacy_status=PrivacyStatus.PRIVATE,
        )

        job = QueueJobModel(
            id=job_id,
            user_id="test-user",
            drive_file_id="test-file-123",
            drive_file_name="video.mp4",
            drive_md5_checksum="abc123",
            folder_path="/test",
            batch_id="batch-001",
            metadata_json=metadata.model_dump_json(),
            status="pending",
            progress=0.0,
            message="",
            retry_count=0,
            max_retries=3,
            created_at=datetime.now(UTC),
        )

        test_session.add(job)
        await test_session.commit()
        await test_session.refresh(job)

        assert job.id == job_id
        assert job.drive_file_id == "test-file-123"
        assert job.status == "pending"

    @pytest.mark.asyncio
    async def test_job_persistence_across_sessions(self, test_engine):
        """Test jobs persist across different database sessions."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        from app.models import QueueJobModel

        session_maker = async_sessionmaker(
            bind=test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        job_id = make_job_id()
        metadata = VideoMetadata(
            title="Persistent Video",
            description="Should persist",
            privacy_status=PrivacyStatus.UNLISTED,
        )

        # Session 1: Create job
        async with session_maker() as session1:
            job = QueueJobModel(
                id=job_id,
                user_id="test-user",
                drive_file_id="persist-file",
                drive_file_name="persist.mp4",
                drive_md5_checksum="persist123",
                metadata_json=metadata.model_dump_json(),
                status="pending",
                progress=0.0,
                message="",
                retry_count=0,
                max_retries=3,
                created_at=datetime.now(UTC),
            )
            session1.add(job)
            await session1.commit()

        # Session 2: Retrieve job
        async with session_maker() as session2:
            result = await session2.execute(
                select(QueueJobModel).where(QueueJobModel.id == job_id)
            )
            retrieved_job = result.scalars().first()

            assert retrieved_job is not None
            assert retrieved_job.drive_file_id == "persist-file"
            assert retrieved_job.status == "pending"

    @pytest.mark.asyncio
    async def test_job_restore_after_restart(self, test_engine):
        """Test jobs can be restored after simulated restart."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        from app.models import QueueJobModel

        session_maker = async_sessionmaker(
            bind=test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # Create multiple pending jobs
        job_ids = []
        async with session_maker() as session:
            for i in range(3):
                job_id = make_job_id()
                job_ids.append(job_id)
                metadata = VideoMetadata(
                    title=f"Video {i}",
                    description=f"Description {i}",
                    privacy_status=PrivacyStatus.PRIVATE,
                )
                job = QueueJobModel(
                    id=job_id,
                    user_id="test-user",
                    drive_file_id=f"file-{i}",
                    drive_file_name=f"video_{i}.mp4",
                    drive_md5_checksum=f"md5-{i}",
                    metadata_json=metadata.model_dump_json(),
                    status="pending",
                    progress=0.0,
                    message="",
                    retry_count=0,
                    max_retries=3,
                    created_at=datetime.now(UTC),
                )
                session.add(job)
            await session.commit()

        # Simulate restart: new session, retrieve all pending jobs
        async with session_maker() as session:
            result = await session.execute(
                select(QueueJobModel).where(QueueJobModel.status == "pending")
            )
            pending_jobs = result.scalars().all()

            assert len(pending_jobs) == 3
            for job in pending_jobs:
                assert job.id in job_ids


class TestQueueOperations:
    """2.2 キュー操作テスト"""

    @pytest.mark.asyncio
    async def test_fifo_order_guarantee(self, test_engine):
        """Test FIFO order is maintained for pending jobs."""
        import asyncio

        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        from app.models import QueueJobModel

        session_maker = async_sessionmaker(
            bind=test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # Create jobs with specific order
        created_order = []
        async with session_maker() as session:
            for i in range(5):
                job_id = make_job_id()
                created_order.append(job_id)
                metadata = VideoMetadata(
                    title=f"FIFO Video {i}",
                    description="",
                    privacy_status=PrivacyStatus.PRIVATE,
                )
                job = QueueJobModel(
                    id=job_id,
                    user_id="test-user",
                    drive_file_id=f"fifo-file-{i}",
                    drive_file_name=f"fifo_{i}.mp4",
                    drive_md5_checksum=f"fifo-md5-{i}",
                    metadata_json=metadata.model_dump_json(),
                    status="pending",
                    progress=0.0,
                    message="",
                    retry_count=0,
                    max_retries=3,
                    created_at=datetime.now(UTC),
                )
                session.add(job)
                await session.commit()
                await asyncio.sleep(0.01)  # Ensure different timestamps

        # Retrieve in FIFO order
        async with session_maker() as session:
            result = await session.execute(
                select(QueueJobModel)
                .where(QueueJobModel.status == "pending")
                .order_by(QueueJobModel.created_at.asc())
            )
            fifo_jobs = result.scalars().all()

            retrieved_order = [job.id for job in fifo_jobs]
            assert retrieved_order == created_order

    @pytest.mark.asyncio
    async def test_job_status_transitions(self, test_session: AsyncSession):
        """Test job status transitions work correctly."""
        from app.models import QueueJobModel

        job_id = make_job_id()
        metadata = VideoMetadata(
            title="Status Test",
            description="",
            privacy_status=PrivacyStatus.PRIVATE,
        )

        job = QueueJobModel(
            id=job_id,
            user_id="test-user",
            drive_file_id="status-file",
            drive_file_name="status.mp4",
            drive_md5_checksum="status-md5",
            metadata_json=metadata.model_dump_json(),
            status="pending",
            progress=0.0,
            message="",
            retry_count=0,
            max_retries=3,
            created_at=datetime.now(UTC),
        )
        test_session.add(job)
        await test_session.commit()

        # Transition: pending -> downloading
        job.status = "downloading"
        job.started_at = datetime.now(UTC)
        job.message = "Downloading from Drive..."
        await test_session.commit()
        await test_session.refresh(job)
        assert job.status == "downloading"
        assert job.started_at is not None

        # Transition: downloading -> uploading
        job.status = "uploading"
        job.progress = 50.0
        job.message = "Uploading to YouTube..."
        await test_session.commit()
        await test_session.refresh(job)
        assert job.status == "uploading"
        assert job.progress == 50.0

        # Transition: uploading -> completed
        job.status = "completed"
        job.progress = 100.0
        job.completed_at = datetime.now(UTC)
        job.video_id = "yt-12345"
        job.video_url = "https://youtube.com/watch?v=yt-12345"
        await test_session.commit()
        await test_session.refresh(job)
        assert job.status == "completed"
        assert job.video_id == "yt-12345"

    @pytest.mark.asyncio
    async def test_error_handling_and_retry(self, test_session: AsyncSession):
        """Test error handling and retry mechanism."""
        from app.models import QueueJobModel

        job_id = make_job_id()
        metadata = VideoMetadata(
            title="Retry Test",
            description="",
            privacy_status=PrivacyStatus.PRIVATE,
        )

        job = QueueJobModel(
            id=job_id,
            user_id="test-user",
            drive_file_id="retry-file",
            drive_file_name="retry.mp4",
            drive_md5_checksum="retry-md5",
            metadata_json=metadata.model_dump_json(),
            status="pending",
            progress=0.0,
            message="",
            retry_count=0,
            max_retries=3,
            created_at=datetime.now(UTC),
        )
        test_session.add(job)
        await test_session.commit()

        # Simulate first failure
        job.status = "pending"  # Reset to pending for retry
        job.retry_count = 1
        job.error = "Network timeout"
        await test_session.commit()

        await test_session.refresh(job)
        assert job.retry_count == 1
        assert job.status == "pending"  # Ready for retry
        assert job.error == "Network timeout"

        # Simulate reaching max retries
        job.retry_count = 3
        job.status = "failed"
        job.error = "Max retries exceeded"
        await test_session.commit()

        await test_session.refresh(job)
        assert job.retry_count == 3
        assert job.status == "failed"

    @pytest.mark.asyncio
    async def test_batch_job_grouping(self, test_session: AsyncSession):
        """Test jobs can be grouped by batch_id."""
        from app.models import QueueJobModel

        batch_id = "batch-group-001"

        # Create multiple jobs in same batch
        for i in range(3):
            metadata = VideoMetadata(
                title=f"Batch Video {i}",
                description="",
                privacy_status=PrivacyStatus.PRIVATE,
            )
            job = QueueJobModel(
                id=make_job_id(),
                user_id="test-user",
                drive_file_id=f"batch-file-{i}",
                drive_file_name=f"batch_{i}.mp4",
                drive_md5_checksum=f"batch-md5-{i}",
                batch_id=batch_id,
                metadata_json=metadata.model_dump_json(),
                status="pending",
                progress=0.0,
                message="",
                retry_count=0,
                max_retries=3,
                created_at=datetime.now(UTC),
            )
            test_session.add(job)

        await test_session.commit()

        # Query by batch
        result = await test_session.execute(
            select(QueueJobModel).where(QueueJobModel.batch_id == batch_id)
        )
        batch_jobs = result.scalars().all()

        assert len(batch_jobs) == 3
        for job in batch_jobs:
            assert job.batch_id == batch_id

    @pytest.mark.asyncio
    async def test_md5_duplicate_detection(self, test_session: AsyncSession):
        """Test MD5 checksum can be used for duplicate detection."""
        from app.models import QueueJobModel

        md5 = "duplicate-md5-checksum"

        # Create first job
        metadata = VideoMetadata(
            title="Original",
            description="",
            privacy_status=PrivacyStatus.PRIVATE,
        )
        job1 = QueueJobModel(
            id=make_job_id(),
            user_id="test-user",
            drive_file_id="original-file",
            drive_file_name="original.mp4",
            drive_md5_checksum=md5,
            metadata_json=metadata.model_dump_json(),
            status="pending",
            progress=0.0,
            message="",
            retry_count=0,
            max_retries=3,
            created_at=datetime.now(UTC),
        )
        test_session.add(job1)
        await test_session.commit()

        # Check for duplicate
        result = await test_session.execute(
            select(QueueJobModel).where(
                QueueJobModel.drive_md5_checksum == md5,
                QueueJobModel.status.in_(["pending", "downloading", "uploading"])
            )
        )
        existing = result.scalars().first()

        assert existing is not None
        assert existing.drive_md5_checksum == md5
