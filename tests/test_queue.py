"""Tests for queue manager."""

from uuid import uuid4

import pytest

from app.queue.manager import QueueManager
from app.queue.schemas import JobStatus, QueueJobCreate
from app.youtube.schemas import PrivacyStatus, VideoMetadata


@pytest.fixture
def queue_manager() -> QueueManager:
    """Create a fresh queue manager for each test."""
    return QueueManager()


@pytest.fixture
def sample_job_create() -> QueueJobCreate:
    """Create a sample job creation request."""
    return QueueJobCreate(
        drive_file_id="test-drive-file-id",
        drive_file_name="test_video.mp4",
        metadata=VideoMetadata(
            title="Test Video",
            description="A test video",
            privacy_status=PrivacyStatus.PRIVATE,
        ),
    )


def test_add_job(queue_manager: QueueManager, sample_job_create: QueueJobCreate) -> None:
    """Test adding a job to the queue."""
    job = queue_manager.add_job(sample_job_create)

    assert job.id is not None
    assert job.drive_file_id == sample_job_create.drive_file_id
    assert job.drive_file_name == sample_job_create.drive_file_name
    assert job.status == JobStatus.PENDING
    assert job.progress == 0.0


def test_get_job(queue_manager: QueueManager, sample_job_create: QueueJobCreate) -> None:
    """Test getting a job by ID."""
    created_job = queue_manager.add_job(sample_job_create)

    fetched_job = queue_manager.get_job(created_job.id)
    assert fetched_job is not None
    assert fetched_job.id == created_job.id


def test_get_job_not_found(queue_manager: QueueManager) -> None:
    """Test getting a non-existent job."""
    job = queue_manager.get_job(uuid4())
    assert job is None


def test_update_job(queue_manager: QueueManager, sample_job_create: QueueJobCreate) -> None:
    """Test updating a job."""
    job = queue_manager.add_job(sample_job_create)

    updated = queue_manager.update_job(
        job.id,
        status=JobStatus.UPLOADING,
        progress=50.0,
        message="Uploading...",
    )

    assert updated is not None
    assert updated.status == JobStatus.UPLOADING
    assert updated.progress == 50.0
    assert updated.message == "Uploading..."
    assert updated.started_at is not None


def test_cancel_job(queue_manager: QueueManager, sample_job_create: QueueJobCreate) -> None:
    """Test cancelling a pending job."""
    job = queue_manager.add_job(sample_job_create)

    cancelled = queue_manager.cancel_job(job.id)
    assert cancelled is not None
    assert cancelled.status == JobStatus.CANCELLED


def test_cancel_completed_job_fails(
    queue_manager: QueueManager, sample_job_create: QueueJobCreate
) -> None:
    """Test that cancelling a completed job fails."""
    job = queue_manager.add_job(sample_job_create)
    queue_manager.update_job(job.id, status=JobStatus.COMPLETED)

    cancelled = queue_manager.cancel_job(job.id)
    assert cancelled is None


def test_delete_job(queue_manager: QueueManager, sample_job_create: QueueJobCreate) -> None:
    """Test deleting a job."""
    job = queue_manager.add_job(sample_job_create)

    result = queue_manager.delete_job(job.id)
    assert result is True

    assert queue_manager.get_job(job.id) is None


def test_get_all_jobs(
    queue_manager: QueueManager, sample_job_create: QueueJobCreate
) -> None:
    """Test getting all jobs."""
    queue_manager.add_job(sample_job_create)
    queue_manager.add_job(sample_job_create)
    queue_manager.add_job(sample_job_create)

    jobs = queue_manager.get_all_jobs()
    assert len(jobs) == 3


def test_get_pending_jobs(
    queue_manager: QueueManager, sample_job_create: QueueJobCreate
) -> None:
    """Test getting pending jobs."""
    job1 = queue_manager.add_job(sample_job_create)
    queue_manager.add_job(sample_job_create)
    queue_manager.update_job(job1.id, status=JobStatus.COMPLETED)

    pending = queue_manager.get_pending_jobs()
    assert len(pending) == 1


def test_get_status(queue_manager: QueueManager, sample_job_create: QueueJobCreate) -> None:
    """Test getting queue status."""
    job1 = queue_manager.add_job(sample_job_create)
    job2 = queue_manager.add_job(sample_job_create)
    queue_manager.add_job(sample_job_create)

    queue_manager.update_job(job1.id, status=JobStatus.COMPLETED)
    queue_manager.update_job(job2.id, status=JobStatus.UPLOADING)

    status = queue_manager.get_status()
    assert status.total_jobs == 3
    assert status.pending_jobs == 1
    assert status.active_jobs == 1
    assert status.completed_jobs == 1


def test_clear_completed(
    queue_manager: QueueManager, sample_job_create: QueueJobCreate
) -> None:
    """Test clearing completed jobs."""
    job1 = queue_manager.add_job(sample_job_create)
    job2 = queue_manager.add_job(sample_job_create)
    queue_manager.add_job(sample_job_create)

    queue_manager.update_job(job1.id, status=JobStatus.COMPLETED)
    queue_manager.update_job(job2.id, status=JobStatus.FAILED)

    cleared = queue_manager.clear_completed()
    assert cleared == 2
    assert len(queue_manager.get_all_jobs()) == 1
