"""Unit tests for queue management routes.

Tests for:
- Get queue status endpoint
- List jobs endpoint
- Add job endpoint
- Get job endpoint
- Cancel job endpoint
- Delete job endpoint
- Clear completed endpoint
- Worker control endpoints
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.queue.schemas import JobStatus, QueueJob, QueueStatus
from app.youtube.schemas import VideoMetadata


@pytest.fixture
def mock_queue_repo():
    """Mock queue repository for tests."""
    repo = MagicMock()
    repo.get_status = AsyncMock(return_value=QueueStatus(
        total_jobs=20,
        pending_jobs=5,
        active_jobs=2,
        completed_jobs=10,
        failed_jobs=2,
        is_processing=True,
    ))
    repo.get_jobs_by_user = AsyncMock(return_value=[])
    repo.get_job = AsyncMock(return_value=None)
    repo.add_job = AsyncMock()
    repo.cancel_job = AsyncMock()
    repo.delete_job = AsyncMock()
    repo.clear_completed = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def mock_queue_worker():
    """Mock queue worker for tests."""
    with patch("app.queue.routes.get_queue_worker") as mock:
        worker = MagicMock()
        worker.is_running.return_value = True
        worker.start = AsyncMock()
        worker.stop = AsyncMock()
        mock.return_value = worker
        yield worker


@pytest.fixture
def test_client_with_mocks(mock_queue_repo):
    """Create test client with mocked dependencies."""
    from app.core.dependencies import get_queue_repository, get_user_id_from_session
    from app.main import app

    # Override dependencies
    async def override_queue_repo():
        return mock_queue_repo

    async def override_user_id():
        return "test_user_123"

    app.dependency_overrides[get_queue_repository] = override_queue_repo
    app.dependency_overrides[get_user_id_from_session] = override_user_id

    client = TestClient(app)
    yield client

    # Clean up overrides
    app.dependency_overrides.clear()


@pytest.fixture
def test_client():
    """Create test client for the FastAPI app."""
    from app.main import app
    return TestClient(app)


@pytest.fixture
def sample_job_id():
    """Generate a sample job ID."""
    return str(uuid4())


@pytest.fixture
def sample_job():
    """Create a sample QueueJob."""
    return QueueJob(
        id=uuid4(),
        drive_file_id="file123",
        drive_file_name="video.mp4",
        status=JobStatus.PENDING,
        progress=0.0,
        user_id="test_user_123",
        created_at=datetime.now(UTC),
        metadata=VideoMetadata(
            title="Test Video",
            description="Test description",
            privacy_status="private",
        ),
    )


@pytest.mark.unit
class TestQueueStatus:
    """Tests for queue status endpoint."""

    def test_get_queue_status_requires_auth(self, test_client):
        """Test that queue status requires authentication."""
        response = test_client.get("/queue/status")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_queue_status_success(self, mock_queue_repo, test_client_with_mocks):
        """Test getting queue status."""
        response = test_client_with_mocks.get("/queue/status")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["pending_jobs"] == 5
        assert data["completed_jobs"] == 10


@pytest.mark.unit
class TestListJobs:
    """Tests for list jobs endpoint."""

    def test_list_jobs_requires_auth(self, test_client):
        """Test that list jobs requires authentication."""
        response = test_client.get("/queue/jobs")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_jobs_success(self, mock_queue_repo, sample_job, test_client_with_mocks):
        """Test listing user's jobs."""
        mock_queue_repo.get_jobs_by_user = AsyncMock(return_value=[sample_job])

        response = test_client_with_mocks.get("/queue/jobs")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "jobs" in data
        assert len(data["jobs"]) == 1


@pytest.mark.unit
class TestAddJob:
    """Tests for add job endpoint."""

    def test_add_job_requires_auth(self, test_client):
        """Test that add job requires authentication."""
        response = test_client.post(
            "/queue/jobs",
            json={
                "drive_file_id": "file123",
                "drive_file_name": "video.mp4",
                "metadata": {
                    "title": "Test Video",
                    "privacy_status": "private",
                },
            },
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_add_job_success(self, mock_queue_repo, sample_job, test_client_with_mocks):
        """Test adding job to queue."""
        mock_queue_repo.add_job = AsyncMock(return_value=sample_job)

        response = test_client_with_mocks.post(
            "/queue/jobs",
            json={
                "drive_file_id": "file123",
                "drive_file_name": "video.mp4",
                "metadata": {
                    "title": "Test Video",
                    "description": "Test",
                    "privacy_status": "private",
                },
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "job" in data


@pytest.mark.unit
class TestGetJob:
    """Tests for get job endpoint."""

    def test_get_job_requires_auth(self, test_client, sample_job_id):
        """Test that get job requires authentication."""
        response = test_client.get(f"/queue/jobs/{sample_job_id}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_job_not_found(self, mock_queue_repo, sample_job_id, test_client_with_mocks):
        """Test getting non-existent job."""
        mock_queue_repo.get_job = AsyncMock(return_value=None)

        response = test_client_with_mocks.get(f"/queue/jobs/{sample_job_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_job_success(self, mock_queue_repo, sample_job, test_client_with_mocks):
        """Test getting existing job."""
        mock_queue_repo.get_job = AsyncMock(return_value=sample_job)

        response = test_client_with_mocks.get(f"/queue/jobs/{sample_job.id}")

        assert response.status_code == status.HTTP_200_OK


@pytest.mark.unit
class TestCancelJob:
    """Tests for cancel job endpoint."""

    def test_cancel_job_requires_auth(self, test_client, sample_job_id):
        """Test that cancel job requires authentication."""
        response = test_client.post(f"/queue/jobs/{sample_job_id}/cancel")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_cancel_job_success(self, mock_queue_repo, sample_job, test_client_with_mocks):
        """Test cancelling a pending job."""
        mock_queue_repo.get_job = AsyncMock(return_value=sample_job)
        cancelled_job = sample_job.model_copy(update={"status": JobStatus.CANCELLED})
        mock_queue_repo.cancel_job = AsyncMock(return_value=cancelled_job)

        response = test_client_with_mocks.post(f"/queue/jobs/{sample_job.id}/cancel")

        assert response.status_code == status.HTTP_200_OK


@pytest.mark.unit
class TestDeleteJob:
    """Tests for delete job endpoint."""

    def test_delete_job_requires_auth(self, test_client, sample_job_id):
        """Test that delete job requires authentication."""
        response = test_client.delete(f"/queue/jobs/{sample_job_id}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_delete_job_active_fails(self, mock_queue_repo, sample_job, test_client_with_mocks):
        """Test that active jobs cannot be deleted."""
        active_job = sample_job.model_copy(update={"status": JobStatus.UPLOADING})
        mock_queue_repo.get_job = AsyncMock(return_value=active_job)

        response = test_client_with_mocks.delete(f"/queue/jobs/{active_job.id}")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_delete_job_success(self, mock_queue_repo, sample_job, test_client_with_mocks):
        """Test deleting completed job."""
        completed_job = sample_job.model_copy(update={"status": JobStatus.COMPLETED})
        mock_queue_repo.get_job = AsyncMock(return_value=completed_job)
        mock_queue_repo.delete_job = AsyncMock()

        response = test_client_with_mocks.delete(f"/queue/jobs/{completed_job.id}")

        assert response.status_code == status.HTTP_200_OK


@pytest.mark.unit
class TestClearCompleted:
    """Tests for clear completed endpoint."""

    def test_clear_completed_requires_auth(self, test_client):
        """Test that clear completed requires authentication."""
        response = test_client.post("/queue/clear")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_clear_completed_success(self, mock_queue_repo, test_client_with_mocks):
        """Test clearing completed jobs."""
        mock_queue_repo.clear_completed = AsyncMock(return_value=5)

        response = test_client_with_mocks.post("/queue/clear")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["cleared_count"] == 5


@pytest.mark.unit
class TestWorkerControl:
    """Tests for worker control endpoints."""

    def test_start_worker(self, test_client, mock_queue_worker):
        """Test starting the worker."""
        response = test_client.post("/queue/worker/start")

        assert response.status_code == status.HTTP_200_OK

    def test_stop_worker(self, test_client, mock_queue_worker):
        """Test stopping the worker."""
        response = test_client.post("/queue/worker/stop")

        assert response.status_code == status.HTTP_200_OK

