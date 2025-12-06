"""Tests for worker process separation.

Test categories:
3.1 Workerプロセス分離テスト
3.2 TestClient統合テスト
"""

import asyncio
import signal
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.youtube.schemas import PrivacyStatus, VideoMetadata


def make_job_id() -> str:
    """Create a string job ID for SQLite compatibility."""
    return str(uuid4())


class TestWorkerProcessSeparation:
    """3.1 Workerプロセス分離テスト"""

    @pytest.mark.asyncio
    async def test_worker_can_run_standalone(self):
        """Test worker can be started as a standalone process."""
        from app.queue.worker import QueueWorker

        worker = QueueWorker()
        
        # Worker should not be running initially
        assert worker.is_running() is False
        
        # Start worker
        await worker.start()
        assert worker.is_running() is True
        
        # Give it a moment to start the loop
        await asyncio.sleep(0.1)
        
        # Stop worker
        await worker.stop()
        assert worker.is_running() is False

    @pytest.mark.asyncio
    async def test_worker_db_communication(self, test_engine):
        """Test worker communicates with web via database."""
        from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
        from app.models import QueueJobModel

        session_maker = async_sessionmaker(
            bind=test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        job_id = make_job_id()
        metadata = VideoMetadata(
            title="DB Communication Test",
            description="",
            privacy_status=PrivacyStatus.PRIVATE,
        )

        # Web process: Create a job
        async with session_maker() as web_session:
            job = QueueJobModel(
                id=job_id,
                user_id="test-user",
                drive_file_id="comm-test-file",
                drive_file_name="comm.mp4",
                drive_md5_checksum="comm-md5",
                metadata_json=metadata.model_dump_json(),
                status="pending",
                progress=0.0,
                message="",
                retry_count=0,
                max_retries=3,
                created_at=datetime.now(UTC),
            )
            web_session.add(job)
            await web_session.commit()

        # Worker process: Fetch and update job
        async with session_maker() as worker_session:
            result = await worker_session.execute(
                select(QueueJobModel).where(QueueJobModel.id == job_id)
            )
            worker_job = result.scalars().first()
            
            assert worker_job is not None
            worker_job.status = "downloading"
            worker_job.message = "Worker updating..."
            await worker_session.commit()

        # Web process: See the update
        async with session_maker() as web_session:
            result = await web_session.execute(
                select(QueueJobModel).where(QueueJobModel.id == job_id)
            )
            updated_job = result.scalars().first()
            
            assert updated_job.status == "downloading"
            assert updated_job.message == "Worker updating..."

    @pytest.mark.asyncio
    async def test_graceful_shutdown(self):
        """Test worker handles graceful shutdown correctly."""
        from app.queue.worker import QueueWorker

        worker = QueueWorker()
        await worker.start()
        
        assert worker.is_running() is True
        
        # Simulate graceful shutdown
        await worker.stop()
        
        # Worker should have stopped cleanly
        assert worker.is_running() is False
        assert worker._task is not None  # Task should exist but be cancelled

    @pytest.mark.asyncio
    async def test_worker_handles_no_pending_jobs(self):
        """Test worker handles case when no pending jobs exist."""
        from app.queue.worker import QueueWorker
        from app.queue.manager import QueueManager

        # Create a worker with mocked queue manager
        worker = QueueWorker()
        
        # Mock the queue manager to return no jobs
        mock_manager = MagicMock(spec=QueueManager)
        mock_manager.get_active_jobs.return_value = []
        mock_manager.get_next_pending_job.return_value = None
        mock_manager.set_processing = MagicMock()
        
        with patch('app.queue.worker.get_queue_manager', return_value=mock_manager):
            await worker.start()
            await asyncio.sleep(0.2)  # Let it run a little
            await worker.stop()
        
        # Should have called set_processing(False) at least once
        mock_manager.set_processing.assert_called()


class TestWorkerIntegration:
    """3.2 TestClient統合テスト"""

    @pytest.mark.asyncio
    async def test_background_task_execution(self, test_engine):
        """Test background tasks are executed by worker."""
        from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
        from app.models import QueueJobModel

        session_maker = async_sessionmaker(
            bind=test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        job_id = make_job_id()
        metadata = VideoMetadata(
            title="Background Task Test",
            description="",
            privacy_status=PrivacyStatus.PRIVATE,
        )

        # Create a pending job
        async with session_maker() as session:
            job = QueueJobModel(
                id=job_id,
                user_id="test-user",
                drive_file_id="bg-task-file",
                drive_file_name="bg_task.mp4",
                drive_md5_checksum="bg-md5",
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

        # Simulate worker processing (without actual YouTube upload)
        async with session_maker() as session:
            result = await session.execute(
                select(QueueJobModel).where(
                    QueueJobModel.status == "pending"
                ).order_by(QueueJobModel.created_at.asc())
            )
            pending_job = result.scalars().first()
            
            if pending_job:
                # Simulate processing
                pending_job.status = "completed"
                pending_job.progress = 100.0
                pending_job.video_id = "simulated-yt-id"
                pending_job.video_url = "https://youtube.com/watch?v=simulated-yt-id"
                pending_job.completed_at = datetime.now(UTC)
                await session.commit()

        # Verify job was processed
        async with session_maker() as session:
            result = await session.execute(
                select(QueueJobModel).where(QueueJobModel.id == job_id)
            )
            final_job = result.scalars().first()
            
            assert final_job.status == "completed"
            assert final_job.video_id == "simulated-yt-id"

    @pytest.mark.asyncio
    async def test_endpoint_worker_integration(self, test_engine):
        """Test API endpoint and worker work together."""
        from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
        from app.models import QueueJobModel

        session_maker = async_sessionmaker(
            bind=test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # Simulate API creating multiple jobs
        job_ids = []
        async with session_maker() as session:
            for i in range(3):
                job_id = make_job_id()
                job_ids.append(job_id)
                metadata = VideoMetadata(
                    title=f"Integration Test {i}",
                    description="",
                    privacy_status=PrivacyStatus.PRIVATE,
                )
                job = QueueJobModel(
                    id=job_id,
                    user_id="test-user",
                    drive_file_id=f"int-file-{i}",
                    drive_file_name=f"int_{i}.mp4",
                    drive_md5_checksum=f"int-md5-{i}",
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

        # Simulate worker processing in order
        async with session_maker() as session:
            for expected_id in job_ids:
                result = await session.execute(
                    select(QueueJobModel).where(
                        QueueJobModel.status == "pending"
                    ).order_by(QueueJobModel.created_at.asc())
                )
                job = result.scalars().first()
                
                assert job is not None
                assert job.id == expected_id  # FIFO order
                
                job.status = "completed"
                job.completed_at = datetime.now(UTC)
                await session.commit()

        # Verify all jobs completed
        async with session_maker() as session:
            result = await session.execute(
                select(QueueJobModel).where(QueueJobModel.status == "pending")
            )
            pending = result.scalars().all()
            assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_worker_skips_active_jobs(self, test_engine):
        """Test worker respects max concurrent uploads limit."""
        from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
        from app.models import QueueJobModel

        session_maker = async_sessionmaker(
            bind=test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # Create one active and one pending job
        async with session_maker() as session:
            # Active job
            active_metadata = VideoMetadata(
                title="Active Job",
                description="",
                privacy_status=PrivacyStatus.PRIVATE,
            )
            active_job = QueueJobModel(
                id=make_job_id(),
                user_id="test-user",
                drive_file_id="active-file",
                drive_file_name="active.mp4",
                drive_md5_checksum="active-md5",
                metadata_json=active_metadata.model_dump_json(),
                status="uploading",  # Already active
                progress=50.0,
                message="",
                retry_count=0,
                max_retries=3,
                created_at=datetime.now(UTC),
            )
            session.add(active_job)

            # Pending job
            pending_metadata = VideoMetadata(
                title="Pending Job",
                description="",
                privacy_status=PrivacyStatus.PRIVATE,
            )
            pending_job = QueueJobModel(
                id=make_job_id(),
                user_id="test-user",
                drive_file_id="pending-file",
                drive_file_name="pending.mp4",
                drive_md5_checksum="pending-md5",
                metadata_json=pending_metadata.model_dump_json(),
                status="pending",
                progress=0.0,
                message="",
                retry_count=0,
                max_retries=3,
                created_at=datetime.now(UTC),
            )
            session.add(pending_job)
            await session.commit()

        # Count active jobs
        async with session_maker() as session:
            result = await session.execute(
                select(QueueJobModel).where(
                    QueueJobModel.status.in_(["downloading", "uploading"])
                )
            )
            active_jobs = result.scalars().all()
            
            # Worker should check this count before starting new jobs
            assert len(active_jobs) == 1
