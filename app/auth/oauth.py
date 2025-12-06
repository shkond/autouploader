"""Google OAuth service for authentication with database persistence."""

import json
import logging
import secrets
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from app.config import get_settings

logger = logging.getLogger(__name__)


class OAuthService:
    """Service for managing Google OAuth authentication with DB persistence.
    
    Tokens are stored encrypted in the database using Fernet encryption.
    Supports multi-user token storage keyed by user_id.
    """

    def __init__(self) -> None:
        """Initialize OAuth service."""
        self.settings = get_settings()
        # In-memory cache for credentials (keyed by user_id)
        self._credentials_cache: dict[str, Credentials] = {}

    async def _load_credentials_from_db(self, user_id: str) -> Credentials | None:
        """Load credentials from database for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            Credentials or None if not found
        """
        from sqlalchemy import select

        from app.crypto import decrypt_token
        from app.database import get_db_context
        from app.models import OAuthToken

        try:
            async with get_db_context() as session:
                result = await session.execute(
                    select(OAuthToken).where(OAuthToken.user_id == user_id)
                )
                token_record = result.scalars().first()

                if not token_record:
                    return None

                # Decrypt tokens
                access_token = decrypt_token(token_record.encrypted_access_token)
                refresh_token = decrypt_token(token_record.encrypted_refresh_token)
                scopes = json.loads(token_record.scopes)

                return Credentials(
                    token=access_token,
                    refresh_token=refresh_token,
                    token_uri=token_record.token_uri,
                    client_id=self.settings.google_client_id,
                    client_secret=self.settings.google_client_secret,
                    scopes=scopes,
                )
        except Exception as e:
            logger.warning(f"Failed to load credentials from DB: {type(e).__name__}")
            logger.debug(f"Credential load error: {e}")
            return None

    async def _save_credentials_to_db(
        self, user_id: str, credentials: Credentials
    ) -> None:
        """Save credentials to database for a user.
        
        Args:
            user_id: User identifier
            credentials: Google credentials to save
        """

        from sqlalchemy import select

        from app.crypto import encrypt_token
        from app.database import get_db_context
        from app.models import OAuthToken

        try:
            encrypted_access = encrypt_token(credentials.token or "")
            encrypted_refresh = encrypt_token(credentials.refresh_token or "")
            scopes_json = json.dumps(list(credentials.scopes or []))

            async with get_db_context() as session:
                # Check if record exists
                result = await session.execute(
                    select(OAuthToken).where(OAuthToken.user_id == user_id)
                )
                existing = result.scalars().first()

                if existing:
                    # Update existing
                    existing.encrypted_access_token = encrypted_access
                    existing.encrypted_refresh_token = encrypted_refresh
                    existing.scopes = scopes_json
                    existing.token_uri = credentials.token_uri or "https://oauth2.googleapis.com/token"
                    if credentials.expiry:
                        existing.expires_at = credentials.expiry
                else:
                    # Create new
                    token_record = OAuthToken(
                        user_id=user_id,
                        encrypted_access_token=encrypted_access,
                        encrypted_refresh_token=encrypted_refresh,
                        scopes=scopes_json,
                        token_uri=credentials.token_uri or "https://oauth2.googleapis.com/token",
                        expires_at=credentials.expiry,
                    )
                    session.add(token_record)

                await session.commit()
                logger.info(f"Saved OAuth credentials for user {user_id}")

        except Exception as e:
            logger.error(f"Failed to save credentials to DB: {type(e).__name__}")
            logger.debug(f"Credential save error: {e}")

    def get_credentials_sync(self, user_id: str) -> Credentials | None:
        """Get cached credentials synchronously (for non-async contexts).
        
        Args:
            user_id: User identifier
            
        Returns:
            Cached credentials or None
        """
        return self._credentials_cache.get(user_id)

    async def get_credentials(self, user_id: str) -> Credentials | None:
        """Get current credentials, refreshing if needed.

        Args:
            user_id: User identifier

        Returns:
            Valid credentials or None if not authenticated
        """
        # Check cache first
        credentials = self._credentials_cache.get(user_id)

        # If not in cache, load from DB
        if not credentials:
            credentials = await self._load_credentials_from_db(user_id)
            if credentials:
                self._credentials_cache[user_id] = credentials

        if not credentials:
            return None

        # Refresh if expired
        if credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
                self._credentials_cache[user_id] = credentials
                await self._save_credentials_to_db(user_id, credentials)
            except Exception as e:
                logger.warning(f"Failed to refresh credentials: {type(e).__name__}")
                self._credentials_cache.pop(user_id, None)
                return None

        return credentials

    async def is_authenticated(self, user_id: str) -> bool:
        """Check if user is authenticated with valid credentials.
        
        Args:
            user_id: User identifier
        """
        creds = await self.get_credentials(user_id)
        return creds is not None and creds.valid

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

    async def exchange_code(
        self, code: str, user_id: str, state: str | None = None
    ) -> Credentials:
        """Exchange authorization code for credentials.

        Args:
            code: Authorization code from OAuth callback
            user_id: User identifier to associate with credentials
            state: OAuth state parameter (optional)

        Returns:
            Google credentials
        """
        flow = self._create_flow()
        if state:
            flow.state = state
        flow.fetch_token(code=code)
        credentials = flow.credentials

        # Cache and save to DB
        self._credentials_cache[user_id] = credentials
        await self._save_credentials_to_db(user_id, credentials)

        return credentials

    async def logout(self, user_id: str) -> None:
        """Clear stored credentials for a user.
        
        Args:
            user_id: User identifier
        """
        from sqlalchemy import delete

        from app.database import get_db_context
        from app.models import OAuthToken

        # Clear cache
        self._credentials_cache.pop(user_id, None)

        # Delete from DB
        try:
            async with get_db_context() as session:
                await session.execute(
                    delete(OAuthToken).where(OAuthToken.user_id == user_id)
                )
                await session.commit()
                logger.info(f"Logged out user {user_id}")
        except Exception as e:
            logger.warning(f"Failed to delete credentials from DB: {type(e).__name__}")

    async def get_user_info(self, user_id: str) -> dict[str, Any] | None:
        """Get authenticated user information from Google.

        Args:
            user_id: User identifier

        Returns:
            User info dict or None if not authenticated or on error
        """
        creds = await self.get_credentials(user_id)
        if not creds:
            return None

        try:
            from googleapiclient.discovery import build

            service = build("oauth2", "v2", credentials=creds)
            return service.userinfo().get().execute()
        except Exception as e:
            logger.warning(f"Failed to get user info: {type(e).__name__}")
            logger.debug(f"User info error details: {e}")
            return None

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
