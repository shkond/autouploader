"""Unit tests for authentication routes.

Tests for:
- Login page rendering
- Login form submission
- Dashboard access
- Google OAuth flow
- Logout functionality
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient


@pytest.fixture
def mock_session_manager():
    """Mock session manager for auth tests."""
    with patch("app.auth.dependencies.get_session_manager") as mock:
        manager = MagicMock()
        mock.return_value = manager
        yield manager


@pytest.fixture
def mock_oauth_service():
    """Mock OAuth service for auth tests."""
    with patch("app.auth.routes.get_oauth_service") as mock:
        service = MagicMock()
        # Make async methods return AsyncMock
        service.is_authenticated = AsyncMock(return_value=False)
        service.get_user_info = AsyncMock(return_value=None)
        service.get_credentials = AsyncMock(return_value=None)
        service.exchange_code = AsyncMock()
        service.logout = AsyncMock()
        mock.return_value = service
        yield service


@pytest.fixture
def test_client():
    """Create test client for the FastAPI app."""
    from app.main import app
    return TestClient(app)


@pytest.mark.unit
class TestLoginPage:
    """Tests for login page endpoint."""

    def test_login_page_renders(self, test_client, mock_session_manager):
        """Test that login page renders successfully."""
        mock_session_manager.verify_session_token.return_value = None

        response = test_client.get("/auth/login")

        assert response.status_code == status.HTTP_200_OK
        assert "text/html" in response.headers["content-type"]

    def test_login_page_redirects_when_authenticated(
        self, test_client, mock_session_manager
    ):
        """Test that authenticated users are redirected to dashboard."""
        mock_session_manager.verify_session_token.return_value = {
            "username": "testuser",
            "user_id": "user123",
        }

        response = test_client.get(
            "/auth/login",
            cookies={"session": "valid-token"},
            follow_redirects=False,
        )

        assert response.status_code == status.HTTP_303_SEE_OTHER
        assert "/auth/dashboard" in response.headers["location"]


@pytest.mark.unit
class TestLoginSubmit:
    """Tests for login form submission."""

    def test_login_submit_success(self, test_client, mock_session_manager):
        """Test successful login redirects to dashboard."""
        mock_session_manager.verify_credentials.return_value = True
        mock_session_manager.create_session_token.return_value = "new-session-token"

        response = test_client.post(
            "/auth/login",
            data={"username": "testuser", "password": "testpass"},
            follow_redirects=False,
        )

        assert response.status_code == status.HTTP_303_SEE_OTHER
        assert "/auth/dashboard" in response.headers["location"]
        assert "session" in response.cookies

    def test_login_submit_invalid_credentials(
        self, test_client, mock_session_manager
    ):
        """Test invalid credentials redirects to login with error."""
        mock_session_manager.verify_credentials.return_value = False

        response = test_client.post(
            "/auth/login",
            data={"username": "wronguser", "password": "wrongpass"},
            follow_redirects=False,
        )

        assert response.status_code == status.HTTP_303_SEE_OTHER
        assert "/auth/login" in response.headers["location"]
        assert "error=" in response.headers["location"]


@pytest.mark.unit
class TestDashboard:
    """Tests for dashboard endpoint."""

    def test_dashboard_requires_auth(self, test_client, mock_session_manager):
        """Test that dashboard redirects unauthenticated users to login."""
        mock_session_manager.verify_session_token.return_value = None

        response = test_client.get(
            "/auth/dashboard",
            follow_redirects=False,
        )

        assert response.status_code == status.HTTP_303_SEE_OTHER
        assert "/auth/login" in response.headers["location"]

    def test_dashboard_renders_for_authenticated_user(
        self, test_client, mock_session_manager, mock_oauth_service
    ):
        """Test that dashboard renders for authenticated users."""
        mock_session_manager.verify_session_token.return_value = {
            "username": "testuser",
            "user_id": "user123",
        }
        mock_oauth_service.is_authenticated.return_value = False

        response = test_client.get(
            "/auth/dashboard",
            cookies={"session": "valid-token"},
        )

        assert response.status_code == status.HTTP_200_OK
        assert "text/html" in response.headers["content-type"]


@pytest.mark.unit
class TestGoogleOAuth:
    """Tests for Google OAuth flow."""

    def test_google_login_redirect(
        self, test_client, mock_session_manager, mock_oauth_service
    ):
        """Test that Google login redirects to OAuth URL."""
        mock_session_manager.verify_session_token.return_value = {
            "username": "testuser",
            "user_id": "user123",
        }
        mock_oauth_service.get_authorization_url.return_value = (
            "https://accounts.google.com/o/oauth2/v2/auth?...",
            "state123",
        )

        response = test_client.get(
            "/auth/google",
            cookies={"session": "valid-token"},
            follow_redirects=False,
        )

        assert response.status_code == status.HTTP_303_SEE_OTHER
        assert "accounts.google.com" in response.headers["location"]

    def test_google_login_requires_auth(
        self, test_client, mock_session_manager
    ):
        """Test that Google login requires app authentication first."""
        mock_session_manager.verify_session_token.return_value = None

        response = test_client.get(
            "/auth/google",
            follow_redirects=False,
        )

        assert response.status_code == status.HTTP_303_SEE_OTHER
        assert "/auth/login" in response.headers["location"]

    def test_oauth_callback_success(
        self, test_client, mock_session_manager, mock_oauth_service
    ):
        """Test successful OAuth callback."""
        mock_session_manager.verify_session_token.return_value = {
            "username": "testuser",
            "user_id": "user123",
        }
        mock_oauth_service.exchange_code.return_value = None

        response = test_client.get(
            "/auth/callback?code=auth-code&state=state123",
            cookies={"session": "valid-token"},
            follow_redirects=False,
        )

        assert response.status_code == status.HTTP_303_SEE_OTHER
        assert "/auth/dashboard" in response.headers["location"]


@pytest.mark.unit
class TestAuthStatus:
    """Tests for auth status endpoint."""

    def test_auth_status_unauthenticated(
        self, test_client, mock_session_manager
    ):
        """Test auth status returns false when not authenticated."""
        mock_session_manager.verify_session_token.return_value = None

        response = test_client.get("/auth/status")

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["authenticated"] is False

    def test_auth_status_authenticated(
        self, test_client, mock_session_manager, mock_oauth_service
    ):
        """Test auth status returns user info when authenticated."""
        mock_session_manager.verify_session_token.return_value = {
            "username": "testuser",
            "user_id": "user123",
        }
        mock_oauth_service.is_authenticated.return_value = True
        mock_oauth_service.get_user_info.return_value = {
            "id": "google123",
            "email": "test@example.com",
            "name": "Test User",
            "picture": "https://example.com/photo.jpg",
        }
        mock_creds = MagicMock()
        mock_creds.scopes = ["scope1", "scope2"]
        mock_oauth_service.get_credentials.return_value = mock_creds

        response = test_client.get(
            "/auth/status",
            cookies={"session": "valid-token"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["authenticated"] is True
        assert data["user"]["email"] == "test@example.com"


@pytest.mark.unit
class TestLogout:
    """Tests for logout endpoint."""

    def test_logout_clears_session(
        self, test_client, mock_session_manager, mock_oauth_service
    ):
        """Test that logout clears session and redirects to login."""
        mock_session_manager.verify_session_token.return_value = {
            "username": "testuser",
            "user_id": "user123",
        }

        response = test_client.get(
            "/auth/logout",
            cookies={"session": "valid-token"},
            follow_redirects=False,
        )

        assert response.status_code == status.HTTP_303_SEE_OTHER
        assert "/auth/login" in response.headers["location"]
        # Check that session cookie is deleted
        assert response.cookies.get("session") == ""
