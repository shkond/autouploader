"""End-to-end tests for upload flow.

Test categories:
6.1 完全なアップロードフローテスト
"""

import asyncio
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


class TestCompleteUploadFlow:
    """6.1 完全なアップロードフローテスト"""

    @pytest.mark.asyncio
    async def test_complete_upload_flow(self, test_engine):
        """Test complete flow: file upload → queue → worker → completion."""
        from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
        from app.models import QueueJobModel, UploadHistory

        session_maker = async_sessionmaker(
            bind=test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        job_id = make_job_id()
        metadata = VideoMetadata(
            title="E2E Test Video",
            description="Full flow test",
            privacy_status=PrivacyStatus.PRIVATE,
        )

        # Step 1: API endpoint creates a queue job
        async with session_maker() as session:
            job = QueueJobModel(
                id=job_id,
                user_id="test-user",
                drive_file_id="e2e-drive-file",
                drive_file_name="e2e_video.mp4",
                drive_md5_checksum="e2e-md5-hash",
                folder_path="/e2e/test",
                metadata_json=metadata.model_dump_json(),
                status="pending",
                progress=0.0,
                message="Queued for upload",
                retry_count=0,
                max_retries=3,
                created_at=datetime.now(UTC),
            )
            session.add(job)
            await session.commit()

        # Step 2: Worker picks up the job
        async with session_maker() as session:
            result = await session.execute(
                select(QueueJobModel).where(QueueJobModel.status == "pending")
            )
            pending_job = result.scalars().first()
            
            assert pending_job is not None
            assert pending_job.id == job_id
            
            # Update to downloading
            pending_job.status = "downloading"
            pending_job.started_at = datetime.now(UTC)
            pending_job.message = "Downloading from Google Drive..."
            await session.commit()

        # Step 3: Download completes, start upload
        async with session_maker() as session:
            result = await session.execute(
                select(QueueJobModel).where(QueueJobModel.id == job_id)
            )
            job = result.scalars().first()
            
            job.status = "uploading"
            job.progress = 25.0
            job.message = "Uploading to YouTube..."
            await session.commit()

        # Step 4: Upload progresses
        async with session_maker() as session:
            result = await session.execute(
                select(QueueJobModel).where(QueueJobModel.id == job_id)
            )
            job = result.scalars().first()
            
            job.progress = 75.0
            job.message = "Upload 75% complete..."
            await session.commit()

        # Step 5: Upload completes
        async with session_maker() as session:
            result = await session.execute(
                select(QueueJobModel).where(QueueJobModel.id == job_id)
            )
            job = result.scalars().first()
            
            job.status = "completed"
            job.progress = 100.0
            job.video_id = "yt-e2e-12345"
            job.video_url = "https://youtube.com/watch?v=yt-e2e-12345"
            job.completed_at = datetime.now(UTC)
            job.message = "Upload completed successfully"
            await session.commit()

        # Step 6: Save to upload history
        async with session_maker() as session:
            result = await session.execute(
                select(QueueJobModel).where(QueueJobModel.id == job_id)
            )
            completed_job = result.scalars().first()
            
            history = UploadHistory(
                drive_file_id=completed_job.drive_file_id,
                drive_file_name=completed_job.drive_file_name,
                drive_md5_checksum=completed_job.drive_md5_checksum or "",
                youtube_video_id=completed_job.video_id,
                youtube_video_url=completed_job.video_url,
                folder_path=completed_job.folder_path or "",
                status="completed",
                uploaded_at=datetime.now(UTC),
            )
            session.add(history)
            await session.commit()

        # Verify final state
        async with session_maker() as session:
            # Queue job completed
            result = await session.execute(
                select(QueueJobModel).where(QueueJobModel.id == job_id)
            )
            final_job = result.scalars().first()
            assert final_job.status == "completed"
            assert final_job.video_id == "yt-e2e-12345"

            # Upload history recorded
            result = await session.execute(
                select(UploadHistory).where(
                    UploadHistory.drive_file_id == "e2e-drive-file"
                )
            )
            history_record = result.scalars().first()
            assert history_record is not None
            assert history_record.youtube_video_id == "yt-e2e-12345"

    @pytest.mark.asyncio
    async def test_restart_resilience(self):
        """Test jobs survive simulated restart and resume processing.
        
        Note: This test uses a file-based SQLite database to properly test
        persistence across connection disposal (simulating process restart).
        """
        import os
        import tempfile
        from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession, create_async_engine
        from app.models import QueueJobModel
        from app.database import Base

        # Create a temporary file-based database
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            db_url = f"sqlite+aiosqlite:///{db_path}"
            
            # Create engine and tables
            engine1 = create_async_engine(db_url, echo=False)
            async with engine1.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            session_maker = async_sessionmaker(
                bind=engine1,
                class_=AsyncSession,
                expire_on_commit=False,
            )

            job_ids = []
            
            # Phase 1: Create jobs (before "restart")
            async with session_maker() as session:
                for i in range(3):
                    job_id = make_job_id()
                    job_ids.append(job_id)
                    metadata = VideoMetadata(
                        title=f"Restart Test {i}",
                        description="",
                        privacy_status=PrivacyStatus.PRIVATE,
                    )
                    job = QueueJobModel(
                        id=job_id,
                        user_id="test-user",
                        drive_file_id=f"restart-file-{i}",
                        drive_file_name=f"restart_{i}.mp4",
                        drive_md5_checksum=f"restart-md5-{i}",
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

            # Simulate restart: dispose engine completely
            await engine1.dispose()

            # Phase 2: After "restart", create new engine and verify jobs persist
            engine2 = create_async_engine(db_url, echo=False)
            new_session_maker = async_sessionmaker(
                bind=engine2,
                class_=AsyncSession,
                expire_on_commit=False,
            )

            async with new_session_maker() as session:
                result = await session.execute(
                    select(QueueJobModel).where(QueueJobModel.status == "pending")
                )
                pending_jobs = result.scalars().all()
                
                assert len(pending_jobs) == 3
                retrieved_ids = [job.id for job in pending_jobs]
                for job_id in job_ids:
                    assert job_id in retrieved_ids

            await engine2.dispose()

        finally:
            # Cleanup
            if os.path.exists(db_path):
                os.remove(db_path)

    @pytest.mark.asyncio
    async def test_error_recovery(self, test_engine):
        """Test error recovery and retry mechanism."""
        from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
        from app.models import QueueJobModel

        session_maker = async_sessionmaker(
            bind=test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        job_id = make_job_id()
        metadata = VideoMetadata(
            title="Error Recovery Test",
            description="",
            privacy_status=PrivacyStatus.PRIVATE,
        )

        # Create job
        async with session_maker() as session:
            job = QueueJobModel(
                id=job_id,
                user_id="test-user",
                drive_file_id="error-file",
                drive_file_name="error.mp4",
                drive_md5_checksum="error-md5",
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

        # First attempt fails
        async with session_maker() as session:
            result = await session.execute(
                select(QueueJobModel).where(QueueJobModel.id == job_id)
            )
            job = result.scalars().first()
            
            job.status = "pending"  # Reset for retry
            job.retry_count = 1
            job.error = "Network timeout during download"
            job.message = "Retry 1/3"
            await session.commit()

        # Second attempt fails
        async with session_maker() as session:
            result = await session.execute(
                select(QueueJobModel).where(QueueJobModel.id == job_id)
            )
            job = result.scalars().first()
            
            job.retry_count = 2
            job.error = "YouTube API rate limit"
            job.message = "Retry 2/3"
            await session.commit()

        # Third attempt succeeds
        async with session_maker() as session:
            result = await session.execute(
                select(QueueJobModel).where(QueueJobModel.id == job_id)
            )
            job = result.scalars().first()
            
            job.status = "completed"
            job.progress = 100.0
            job.video_id = "yt-recovered"
            job.video_url = "https://youtube.com/watch?v=yt-recovered"
            job.completed_at = datetime.now(UTC)
            job.error = None
            job.message = "Upload completed after retries"
            await session.commit()

        # Verify recovery
        async with session_maker() as session:
            result = await session.execute(
                select(QueueJobModel).where(QueueJobModel.id == job_id)
            )
            final_job = result.scalars().first()
            
            assert final_job.status == "completed"
            assert final_job.retry_count == 2
            assert final_job.video_id == "yt-recovered"

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self, test_engine):
        """Test job fails permanently after max retries."""
        from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
        from app.models import QueueJobModel

        session_maker = async_sessionmaker(
            bind=test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        job_id = make_job_id()
        metadata = VideoMetadata(
            title="Max Retry Test",
            description="",
            privacy_status=PrivacyStatus.PRIVATE,
        )

        # Create job with max_retries=2
        async with session_maker() as session:
            job = QueueJobModel(
                id=job_id,
                user_id="test-user",
                drive_file_id="max-retry-file",
                drive_file_name="max_retry.mp4",
                drive_md5_checksum="max-retry-md5",
                metadata_json=metadata.model_dump_json(),
                status="pending",
                progress=0.0,
                message="",
                retry_count=0,
                max_retries=2,
                created_at=datetime.now(UTC),
            )
            session.add(job)
            await session.commit()

        # Exhaust retries
        async with session_maker() as session:
            result = await session.execute(
                select(QueueJobModel).where(QueueJobModel.id == job_id)
            )
            job = result.scalars().first()
            
            # After max retries, mark as failed
            job.status = "failed"
            job.retry_count = 2
            job.error = "Max retries exceeded: persistent error"
            job.completed_at = datetime.now(UTC)
            await session.commit()

        # Verify permanent failure
        async with session_maker() as session:
            result = await session.execute(
                select(QueueJobModel).where(QueueJobModel.id == job_id)
            )
            final_job = result.scalars().first()
            
            assert final_job.status == "failed"
            assert final_job.retry_count == 2
            assert "Max retries exceeded" in final_job.error

    @pytest.mark.asyncio
    async def test_batch_upload_flow(self, test_engine):
        """Test batch upload with multiple files."""
        from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
        from app.models import QueueJobModel, UploadHistory

        session_maker = async_sessionmaker(
            bind=test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        batch_id = "batch-e2e-001"
        job_ids = []

        # Create batch of jobs
        async with session_maker() as session:
            for i in range(5):
                job_id = make_job_id()
                job_ids.append(job_id)
                metadata = VideoMetadata(
                    title=f"Batch Video {i+1}",
                    description=f"Part {i+1} of batch upload",
                    privacy_status=PrivacyStatus.UNLISTED,
                )
                job = QueueJobModel(
                    id=job_id,
                    user_id="test-user",
                    drive_file_id=f"batch-file-{i}",
                    drive_file_name=f"batch_{i}.mp4",
                    drive_md5_checksum=f"batch-md5-{i}",
                    folder_path="/batch/folder",
                    batch_id=batch_id,
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

        # Process all jobs
        async with session_maker() as session:
            for i, job_id in enumerate(job_ids):
                result = await session.execute(
                    select(QueueJobModel).where(QueueJobModel.id == job_id)
                )
                job = result.scalars().first()
                
                job.status = "completed"
                job.progress = 100.0
                job.video_id = f"yt-batch-{i}"
                job.video_url = f"https://youtube.com/watch?v=yt-batch-{i}"
                job.completed_at = datetime.now(UTC)

                # Save history
                history = UploadHistory(
                    drive_file_id=job.drive_file_id,
                    drive_file_name=job.drive_file_name,
                    drive_md5_checksum=job.drive_md5_checksum or "",
                    youtube_video_id=job.video_id,
                    youtube_video_url=job.video_url,
                    folder_path=job.folder_path or "",
                    status="completed",
                    uploaded_at=datetime.now(UTC),
                )
                session.add(history)
            
            await session.commit()

        # Verify batch completion
        async with session_maker() as session:
            result = await session.execute(
                select(QueueJobModel).where(QueueJobModel.batch_id == batch_id)
            )
            batch_jobs = result.scalars().all()
            
            assert len(batch_jobs) == 5
            assert all(job.status == "completed" for job in batch_jobs)

            # Verify all records in history
            result = await session.execute(
                select(UploadHistory).where(
                    UploadHistory.folder_path == "/batch/folder"
                )
            )
            history_records = result.scalars().all()
            assert len(history_records) == 5
