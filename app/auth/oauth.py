"""Google OAuth service for authentication."""

import json
import secrets
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from app.config import get_settings


class OAuthService:
    """Service for managing Google OAuth authentication."""

    TOKEN_FILE = Path("token.json")

    def __init__(self) -> None:
        """Initialize OAuth service."""
        self.settings = get_settings()
        self._credentials: Credentials | None = None
        self._load_credentials()

    def _load_credentials(self) -> None:
        """Load credentials from token file if exists."""
        if self.TOKEN_FILE.exists():
            try:
                with open(self.TOKEN_FILE, encoding="utf-8") as f:
                    token_data = json.load(f)
                self._credentials = Credentials(
                    token=token_data.get("access_token"),
                    refresh_token=token_data.get("refresh_token"),
                    token_uri=token_data.get(
                        "token_uri", "https://oauth2.googleapis.com/token"
                    ),
                    client_id=self.settings.google_client_id,
                    client_secret=self.settings.google_client_secret,
                    scopes=token_data.get("scopes", self.settings.scopes_list),
                )
            except (json.JSONDecodeError, KeyError):
                self._credentials = None

    def _save_credentials(self) -> None:
        """Save credentials to token file with secure permissions."""
        import os
        import stat

        if self._credentials:
            token_data = {
                "access_token": self._credentials.token,
                "refresh_token": self._credentials.refresh_token,
                "token_uri": self._credentials.token_uri,
                "scopes": list(self._credentials.scopes or []),
            }
            # Write to a temporary file first, then rename for atomicity
            temp_file = self.TOKEN_FILE.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(token_data, f)
            # Set restrictive permissions (owner read/write only)
            os.chmod(temp_file, stat.S_IRUSR | stat.S_IWUSR)
            # Rename to final location
            temp_file.rename(self.TOKEN_FILE)

    def get_authorization_url(self) -> tuple[str, str]:
        """Generate OAuth authorization URL.

        Returns:
            Tuple of (authorization_url, state)
        """
        flow = self._create_flow()
        state = secrets.token_urlsafe(32)
        flow.state = state
        authorization_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state,
        )
        return authorization_url, state

    def exchange_code(self, code: str, state: str | None = None) -> Credentials:
        """Exchange authorization code for credentials.

        Args:
            code: Authorization code from OAuth callback
            state: OAuth state parameter (optional)

        Returns:
            Google credentials
        """
        flow = self._create_flow()
        if state:
            flow.state = state
        flow.fetch_token(code=code)
        self._credentials = flow.credentials
        self._save_credentials()
        return self._credentials

    def get_credentials(self) -> Credentials | None:
        """Get current credentials, refreshing if needed.

        Returns:
            Valid credentials or None if not authenticated
        """
        if not self._credentials:
            return None

        if self._credentials.expired and self._credentials.refresh_token:
            try:
                self._credentials.refresh(Request())
                self._save_credentials()
            except Exception:
                self._credentials = None
                return None

        return self._credentials

    def is_authenticated(self) -> bool:
        """Check if user is authenticated with valid credentials."""
        creds = self.get_credentials()
        return creds is not None and creds.valid

    def logout(self) -> None:
        """Clear stored credentials."""
        self._credentials = None
        if self.TOKEN_FILE.exists():
            self.TOKEN_FILE.unlink()

    def get_user_info(self) -> dict[str, Any] | None:
        """Get authenticated user information from Google.

        Returns:
            User info dict or None if not authenticated
        """
        creds = self.get_credentials()
        if not creds:
            return None

        from googleapiclient.discovery import build

        service = build("oauth2", "v2", credentials=creds)
        return service.userinfo().get().execute()

    def _create_flow(self) -> Flow:
        """Create OAuth flow from settings."""
        client_config = {
            "web": {
                "client_id": self.settings.google_client_id,
                "client_secret": self.settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [self.settings.google_redirect_uri],
            }
        }
        return Flow.from_client_config(
            client_config,
            scopes=self.settings.scopes_list,
            redirect_uri=self.settings.google_redirect_uri,
        )


# Singleton instance
_oauth_service: OAuthService | None = None


def get_oauth_service() -> OAuthService:
    """Get or create OAuth service singleton."""
    global _oauth_service
    if _oauth_service is None:
        _oauth_service = OAuthService()
    return _oauth_service
