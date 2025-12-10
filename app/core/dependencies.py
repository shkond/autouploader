"""Dependency Injection configuration for the application.

This module provides FastAPI dependencies for injecting services and repositories
into route handlers. It centralizes all DI configuration for easier management
and testing.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from fastapi import Cookie, Depends, HTTPException, status
from google.oauth2.credentials import Credentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

if TYPE_CHECKING:
    from app.auth.oauth import OAuthService
    from app.drive.services import DriveService
    from app.queue.repositories import QueueRepository
    from app.queue.services import QueueService
    from app.youtube.service import YouTubeService


# =============================================================================
# Credential Dependencies
# =============================================================================


async def get_user_credentials(
    session_token: str | None = Cookie(None, alias="session"),
) -> Credentials:
    """Get Google OAuth credentials for the current user.

    This dependency extracts the user_id from the session and retrieves
    their stored OAuth credentials.

    Args:
        session_token: Session cookie value

    Returns:
        Valid Google OAuth credentials

    Raises:
        HTTPException: If not authenticated or credentials invalid
    """
    from app.auth.oauth import get_oauth_service
    from app.auth.simple_auth import get_session_manager

    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    session_manager = get_session_manager()
    session_data = session_manager.verify_session_token(session_token)

    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired",
        )

    user_id = session_data.get("user_id") or session_data.get("username")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User identification not found",
        )

    oauth_service = get_oauth_service()
    credentials = await oauth_service.get_credentials(user_id)

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google authentication required",
            headers={"Location": "/auth/google"},
        )

    return credentials


async def get_optional_credentials(
    session_token: str | None = Cookie(None, alias="session"),
) -> Credentials | None:
    """Get Google OAuth credentials if available (non-throwing version).

    Args:
        session_token: Session cookie value

    Returns:
        Google OAuth credentials or None if not authenticated
    """
    from app.auth.oauth import get_oauth_service
    from app.auth.simple_auth import get_session_manager

    if not session_token:
        return None

    session_manager = get_session_manager()
    session_data = session_manager.verify_session_token(session_token)

    if not session_data:
        return None

    user_id = session_data.get("user_id") or session_data.get("username")
    if not user_id:
        return None

    oauth_service = get_oauth_service()
    return await oauth_service.get_credentials(user_id)


def get_oauth_service_dep() -> OAuthService:
    """Get OAuthService instance.

    Returns:
        OAuthService singleton instance
    """
    from app.auth.oauth import get_oauth_service

    return get_oauth_service()


async def get_session_data(
    session_token: str | None = Cookie(None, alias="session"),
) -> dict | None:
    """Get session data from session token.

    Args:
        session_token: Session cookie value

    Returns:
        Session data dict or None if not authenticated
    """
    from app.auth.simple_auth import get_session_manager

    if not session_token:
        return None

    session_manager = get_session_manager()
    return session_manager.verify_session_token(session_token)


async def require_session(
    session_token: str | None = Cookie(None, alias="session"),
) -> dict:
    """Require valid session, raising HTTPException if not authenticated.

    Args:
        session_token: Session cookie value

    Returns:
        Session data dict

    Raises:
        HTTPException: If not authenticated
    """
    from app.auth.simple_auth import get_session_manager

    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    session_manager = get_session_manager()
    session_data = session_manager.verify_session_token(session_token)

    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired",
        )

    return session_data


# =============================================================================
# Service Dependencies
# =============================================================================


async def get_drive_service(
    credentials: Credentials = Depends(get_user_credentials),
) -> DriveService:
    """Get DriveService instance with user credentials.

    Args:
        credentials: User's Google OAuth credentials (injected)

    Returns:
        DriveService configured for the user
    """
    from app.drive.services import DriveService

    return DriveService(credentials=credentials)


async def get_youtube_service(
    credentials: Credentials = Depends(get_user_credentials),
) -> YouTubeService:
    """Get YouTubeService instance with user credentials.

    Args:
        credentials: User's Google OAuth credentials (injected)

    Returns:
        YouTubeService configured for the user
    """
    from app.youtube.service import YouTubeService

    return YouTubeService(credentials)


async def get_drive_service_from_credentials(
    credentials: Credentials,
) -> DriveService:
    """Get DriveService from explicit credentials (for worker/background tasks).

    Args:
        credentials: Google OAuth credentials

    Returns:
        DriveService configured with the credentials
    """
    from app.drive.service import DriveService

    return DriveService(credentials)


async def get_youtube_service_from_credentials(
    credentials: Credentials,
) -> YouTubeService:
    """Get YouTubeService from explicit credentials (for worker/background tasks).

    Args:
        credentials: Google OAuth credentials

    Returns:
        YouTubeService configured with the credentials
    """
    from app.youtube.service import YouTubeService

    return YouTubeService(credentials)


# =============================================================================
# Repository Dependencies
# =============================================================================


async def get_queue_repository(
    db: AsyncSession = Depends(get_db),
) -> AsyncGenerator[QueueRepository, None]:
    """Get QueueRepository instance with database session.

    Args:
        db: Database session (injected)

    Yields:
        QueueRepository instance
    """
    from app.queue.repositories import QueueRepository

    yield QueueRepository(db)


async def get_queue_service(
    db: AsyncSession = Depends(get_db),
) -> AsyncGenerator[QueueService, None]:
    """Get QueueService instance with database session.

    Args:
        db: Database session (injected)

    Yields:
        QueueService instance
    """
    from app.queue.services import QueueService

    yield QueueService(db=db)


# =============================================================================
# Combined Dependencies (for convenience)
# =============================================================================


async def get_user_id_from_session(
    session_token: str | None = Cookie(None, alias="session"),
) -> str:
    """Extract user_id from session token.

    Args:
        session_token: Session cookie value

    Returns:
        User ID string

    Raises:
        HTTPException: If not authenticated
    """
    from app.auth.simple_auth import get_session_manager

    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    session_manager = get_session_manager()
    session_data = session_manager.verify_session_token(session_token)

    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired",
        )

    user_id = session_data.get("user_id") or session_data.get("username")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User identification not found",
        )

    return user_id
