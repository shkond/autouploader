"""Simple session-based authentication for app access."""

import hmac
import time
from typing import Any

from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.config import get_settings


class SessionManager:
    """Manage signed cookie sessions for authentication."""

    SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days

    def __init__(self) -> None:
        """Initialize session manager with settings."""
        self.settings = get_settings()
        self._serializer = URLSafeTimedSerializer(self.settings.secret_key)

    def verify_credentials(self, username: str, password: str) -> bool:
        """Verify username and password against environment settings.

        Args:
            username: Provided username
            password: Provided password

        Returns:
            True if credentials match
        """
        if not self.settings.auth_username or not self.settings.auth_password:
            return False

        # Use constant-time comparison to prevent timing attacks
        username_match = hmac.compare_digest(
            username.encode(), self.settings.auth_username.encode()
        )
        password_match = hmac.compare_digest(
            password.encode(), self.settings.auth_password.encode()
        )

        return username_match and password_match

    def create_session_token(self, username: str) -> str:
        """Create a signed session token.

        Args:
            username: Authenticated username

        Returns:
            Signed session token
        """
        session_data = {
            "username": username,
            "user_id": username,  # Use username as user_id for Simple Auth
            "created_at": int(time.time()),
        }
        return self._serializer.dumps(session_data)

    def verify_session_token(self, token: str) -> dict[str, Any] | None:
        """Verify and decode a session token.

        Args:
            token: Session token from cookie

        Returns:
            Session data dict or None if invalid/expired
        """
        try:
            session_data = self._serializer.loads(token, max_age=self.SESSION_MAX_AGE)
            return session_data
        except BadSignature:
            return None


# Singleton instance
_session_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    """Get or create session manager singleton."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
