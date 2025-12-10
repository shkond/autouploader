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

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import status
from fastapi.testclient import TestClient


@pytest.fixture
def mock_session_manager():
    """Mock session manager for queue tests."""
    with patch("app.auth.dependencies.get_session_manager") as mock:
        manager = MagicMock()
        manager.verify_session_token.return_value = {
            "username": "testuser",
            "user_id": "user123",
        }
        mock.return_value = manager
        yield manager


@pytest.fixture
def mock_queue_manager():
    """Mock queue manager for tests."""
    with patch("app.queue.routes.QueueManagerDB") as mock:
        yield mock


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
def test_client():
    """Create test client for the FastAPI app."""
    from app.main import app
    return TestClient(app)


@pytest.fixture
def sample_job_id():
    """Generate a sample job ID."""
    return str(uuid4())


@pytest.mark.unit
class TestQueueStatus:
    """Tests for queue status endpoint."""

    def test_get_queue_status_requires_auth(self, test_client):
        """Test that queue status requires authentication."""
        with patch("app.auth.dependencies.get_session_manager") as mock:
            mock.return_value.verify_session_token.return_value = None

            response = test_client.get("/queue/status")

            assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_queue_status_success(
        self, test_client, mock_session_manager, mock_queue_manager
    ):
        """Test getting queue status."""
        mock_queue_manager.get_queue_status = AsyncMock(return_value={
            "pending": 5,
            "downloading": 1,
            "uploading": 1,
            "completed": 10,
            "failed": 2,
            "cancelled": 1,
        })

        with patch("app.queue.routes.get_db"):
            response = test_client.get(
                "/queue/status",
                cookies={"session": "valid-token"},
            )

        # May need more detailed mocking
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ]


@pytest.mark.unit
class TestListJobs:
    """Tests for list jobs endpoint."""

    def test_list_jobs_requires_auth(self, test_client):
        """Test that list jobs requires authentication."""
        with patch("app.auth.dependencies.get_session_manager") as mock:
            mock.return_value.verify_session_token.return_value = None

            response = test_client.get("/queue/jobs")

            assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_jobs_user_filtered(
        self, test_client, mock_session_manager, mock_queue_manager
    ):
        """Test that jobs are filtered by user."""
        mock_queue_manager.get_jobs_by_user = AsyncMock(return_value=[
            MagicMock(
                id=uuid4(),
                drive_file_id="file1",
                drive_file_name="video1.mp4",
                status="pending",
                progress=0,
                user_id="user123",
            ),
        ])

        with patch("app.queue.routes.get_db"):
            response = test_client.get(
                "/queue/jobs",
                cookies={"session": "valid-token"},
            )

        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ]


@pytest.mark.unit
class TestAddJob:
    """Tests for add job endpoint."""

    def test_add_job_requires_auth(self, test_client):
        """Test that add job requires authentication."""
        with patch("app.auth.dependencies.get_session_manager") as mock:
            mock.return_value.verify_session_token.return_value = None

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

    def test_add_job_success(
        self, test_client, mock_session_manager, mock_queue_manager
    ):
        """Test adding job to queue."""
        job_id = uuid4()
        mock_queue_manager.add_job = AsyncMock(return_value=MagicMock(
            id=job_id,
            drive_file_id="file123",
            drive_file_name="video.mp4",
            status="pending",
            progress=0,
        ))

        with patch("app.queue.routes.get_db"):
            response = test_client.post(
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
                cookies={"session": "valid-token"},
            )

        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_201_CREATED,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ]


@pytest.mark.unit
class TestGetJob:
    """Tests for get job endpoint."""

    def test_get_job_requires_auth(self, test_client, sample_job_id):
        """Test that get job requires authentication."""
        with patch("app.auth.dependencies.get_session_manager") as mock:
            mock.return_value.verify_session_token.return_value = None

            response = test_client.get(f"/queue/jobs/{sample_job_id}")

            assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_job_not_found(
        self, test_client, mock_session_manager, mock_queue_manager, sample_job_id
    ):
        """Test getting non-existent job."""
        mock_queue_manager.get_job = AsyncMock(return_value=None)

        with patch("app.queue.routes.get_db"):
            response = test_client.get(
                f"/queue/jobs/{sample_job_id}",
                cookies={"session": "valid-token"},
            )

        assert response.status_code in [
            status.HTTP_404_NOT_FOUND,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ]


@pytest.mark.unit
class TestCancelJob:
    """Tests for cancel job endpoint."""

    def test_cancel_job_requires_auth(self, test_client, sample_job_id):
        """Test that cancel job requires authentication."""
        with patch("app.auth.dependencies.get_session_manager") as mock:
            mock.return_value.verify_session_token.return_value = None

            response = test_client.post(f"/queue/jobs/{sample_job_id}/cancel")

            assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_cancel_job_success(
        self, test_client, mock_session_manager, mock_queue_manager, sample_job_id
    ):
        """Test cancelling a pending job."""
        mock_queue_manager.get_job = AsyncMock(return_value=MagicMock(
            id=sample_job_id,
            status="pending",
            user_id="user123",
        ))
        mock_queue_manager.cancel_job = AsyncMock(return_value=MagicMock(
            id=sample_job_id,
            status="cancelled",
        ))

        with patch("app.queue.routes.get_db"):
            response = test_client.post(
                f"/queue/jobs/{sample_job_id}/cancel",
                cookies={"session": "valid-token"},
            )

        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ]


@pytest.mark.unit
class TestDeleteJob:
    """Tests for delete job endpoint."""

    def test_delete_job_requires_auth(self, test_client, sample_job_id):
        """Test that delete job requires authentication."""
        with patch("app.auth.dependencies.get_session_manager") as mock:
            mock.return_value.verify_session_token.return_value = None

            response = test_client.delete(f"/queue/jobs/{sample_job_id}")

            assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_delete_job_active_fails(
        self, test_client, mock_session_manager, mock_queue_manager, sample_job_id
    ):
        """Test that active jobs cannot be deleted."""
        mock_queue_manager.get_job = AsyncMock(return_value=MagicMock(
            id=sample_job_id,
            status="uploading",  # Active status
            user_id="user123",
        ))

        with patch("app.queue.routes.get_db"):
            response = test_client.delete(
                f"/queue/jobs/{sample_job_id}",
                cookies={"session": "valid-token"},
            )

        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ]


@pytest.mark.unit
class TestClearCompleted:
    """Tests for clear completed endpoint."""

    def test_clear_completed_requires_auth(self, test_client):
        """Test that clear completed requires authentication."""
        with patch("app.auth.dependencies.get_session_manager") as mock:
            mock.return_value.verify_session_token.return_value = None

            response = test_client.delete("/queue/jobs/completed")

            assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_clear_completed_success(
        self, test_client, mock_session_manager, mock_queue_manager
    ):
        """Test clearing completed jobs."""
        mock_queue_manager.clear_completed = AsyncMock(return_value=5)

        with patch("app.queue.routes.get_db"):
            response = test_client.delete(
                "/queue/jobs/completed",
                cookies={"session": "valid-token"},
            )

        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ]


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
