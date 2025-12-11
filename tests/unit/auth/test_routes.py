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
def mock_oauth_service():
    """Mock OAuth service for auth tests."""
    service = MagicMock()
    # Make async methods return AsyncMock
    service.is_authenticated = AsyncMock(return_value=False)
    service.get_user_info = AsyncMock(return_value=None)
    service.get_credentials = AsyncMock(return_value=None)
    service.exchange_code = AsyncMock()
    service.logout = AsyncMock()
    service.get_authorization_url = MagicMock(return_value=(
        "https://accounts.google.com/o/oauth2/v2/auth?...",
        "state123",
    ))
    return service


@pytest.fixture
def session_data():
    """Sample session data."""
    return {
        "username": "testuser",
        "user_id": "user123",
    }


@pytest.fixture
def test_client_with_session(session_data, mock_oauth_service):
    """Create test client with authenticated session."""
    from app.core.dependencies import get_oauth_service_dep, get_session_data
    from app.main import app

    # Override dependencies
    async def override_session_data():
        return session_data

    def override_oauth_service():
        return mock_oauth_service

    app.dependency_overrides[get_session_data] = override_session_data
    app.dependency_overrides[get_oauth_service_dep] = override_oauth_service

    client = TestClient(app)
    yield client

    # Clean up overrides
    app.dependency_overrides.clear()


@pytest.fixture
def test_client_no_session(mock_oauth_service):
    """Create test client without session."""
    from app.core.dependencies import get_oauth_service_dep, get_session_data
    from app.main import app

    # Override dependencies
    async def override_no_session():
        return None

    def override_oauth_service():
        return mock_oauth_service

    app.dependency_overrides[get_session_data] = override_no_session
    app.dependency_overrides[get_oauth_service_dep] = override_oauth_service

    client = TestClient(app)
    yield client

    # Clean up overrides
    app.dependency_overrides.clear()


@pytest.fixture
def test_client():
    """Create test client for the FastAPI app."""
    from app.main import app
    return TestClient(app)


@pytest.mark.unit
class TestLoginPage:
    """Tests for login page endpoint."""

    @staticmethod
    def test_login_page_renders(test_client_no_session):
        """Test that login page renders successfully."""
        response = test_client_no_session.get("/auth/login")

        assert response.status_code == status.HTTP_200_OK
        assert "text/html" in response.headers["content-type"]

    @staticmethod
    def test_login_page_redirects_when_authenticated(test_client_with_session):
        """Test that authenticated users are redirected to dashboard."""
        response = test_client_with_session.get(
            "/auth/login",
            follow_redirects=False,
        )

        assert response.status_code == status.HTTP_303_SEE_OTHER
        assert "/auth/dashboard" in response.headers["location"]


@pytest.mark.unit
class TestLoginSubmit:
    """Tests for login form submission."""

    @staticmethod
    def test_login_submit_success(test_client):
        """Test successful login redirects to dashboard."""
        with patch("app.auth.routes.get_session_manager") as mock_sm:
            manager = MagicMock()
            manager.verify_credentials.return_value = True
            manager.create_session_token.return_value = "new-session-token"
            mock_sm.return_value = manager

            response = test_client.post(
                "/auth/login",
                data={"username": "testuser", "password": "testpass"},
                follow_redirects=False,
            )

            assert response.status_code == status.HTTP_303_SEE_OTHER
            assert "/auth/dashboard" in response.headers["location"]

    @staticmethod
    def test_login_submit_invalid_credentials(test_client):
        """Test invalid credentials redirects to login with error."""
        with patch("app.auth.routes.get_session_manager") as mock_sm:
            manager = MagicMock()
            manager.verify_credentials.return_value = False
            mock_sm.return_value = manager

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

    @staticmethod
    def test_dashboard_requires_auth(test_client_no_session):
        """Test that dashboard redirects unauthenticated users to login."""
        response = test_client_no_session.get(
            "/auth/dashboard",
            follow_redirects=False,
        )

        assert response.status_code == status.HTTP_303_SEE_OTHER
        assert "/auth/login" in response.headers["location"]

    @staticmethod
    def test_dashboard_renders_for_authenticated_user(
        mock_oauth_service, test_client_with_session
    ):
        """Test that dashboard renders for authenticated users."""
        mock_oauth_service.is_authenticated.return_value = False

        response = test_client_with_session.get("/auth/dashboard")

        assert response.status_code == status.HTTP_200_OK
        assert "text/html" in response.headers["content-type"]


@pytest.mark.unit
class TestGoogleOAuth:
    """Tests for Google OAuth flow."""

    @staticmethod
    def test_google_login_redirect(mock_oauth_service, test_client_with_session):
        """Test that Google login redirects to OAuth URL."""
        response = test_client_with_session.get(
            "/auth/google",
            follow_redirects=False,
        )

        assert response.status_code == status.HTTP_303_SEE_OTHER
        assert "accounts.google.com" in response.headers["location"]

    @staticmethod
    def test_google_login_requires_auth(test_client_no_session):
        """Test that Google login requires app authentication first."""
        response = test_client_no_session.get(
            "/auth/google",
            follow_redirects=False,
        )

        assert response.status_code == status.HTTP_303_SEE_OTHER
        assert "/auth/login" in response.headers["location"]

    @staticmethod
    def test_oauth_callback_success(mock_oauth_service, test_client_with_session):
        """Test successful OAuth callback."""
        mock_oauth_service.exchange_code.return_value = None

        response = test_client_with_session.get(
            "/auth/callback?code=auth-code&state=state123",
            follow_redirects=False,
        )

        assert response.status_code == status.HTTP_303_SEE_OTHER
        assert "/auth/dashboard" in response.headers["location"]


@pytest.mark.unit
class TestAuthStatus:
    """Tests for auth status endpoint."""

    @staticmethod
    def test_auth_status_unauthenticated(test_client_no_session):
        """Test auth status returns false when not authenticated."""
        response = test_client_no_session.get("/auth/status")

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["authenticated"] is False

    @staticmethod
    def test_auth_status_authenticated(mock_oauth_service, test_client_with_session):
        """Test auth status returns user info when authenticated."""
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

        response = test_client_with_session.get("/auth/status")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["authenticated"] is True
        assert data["user"]["email"] == "test@example.com"


@pytest.mark.unit
class TestLogout:
    """Tests for logout endpoint."""

    @staticmethod
    def test_logout_clears_session(mock_oauth_service, test_client_with_session):
        """Test that logout clears session and redirects to login."""
        response = test_client_with_session.get(
            "/auth/logout",
            follow_redirects=False,
        )

        assert response.status_code == status.HTTP_303_SEE_OTHER
        assert "/auth/login" in response.headers["location"]
        mock_oauth_service.logout.assert_called_once()

