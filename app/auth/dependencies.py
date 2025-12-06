"""Authentication dependencies for route protection."""

from fastapi import Cookie, HTTPException, Request, status

from app.auth.oauth import get_oauth_service
from app.auth.simple_auth import get_session_manager


async def require_app_auth(
    request: Request,
    session_token: str | None = Cookie(None, alias="session"),
) -> dict:
    """Dependency that requires app (simple) authentication.

    Args:
        request: FastAPI request object
        session_token: Session cookie value

    Returns:
        Session data dict

    Raises:
        HTTPException: If not authenticated (redirects to login)
    """
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/auth/login"},
            detail="Authentication required",
        )

    session_manager = get_session_manager()
    session_data = session_manager.verify_session_token(session_token)

    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/auth/login"},
            detail="Session expired",
        )

    return session_data


async def require_google_auth(
    session_data: dict = None,
) -> dict:
    """Dependency that requires Google OAuth authentication.

    Args:
        session_data: Session data from app auth (optional)

    Returns:
        User info dict from Google

    Raises:
        HTTPException: If not authenticated with Google
    """
    oauth_service = get_oauth_service()

    if not oauth_service.is_authenticated():
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/auth/google"},
            detail="Google authentication required",
        )

    user_info = oauth_service.get_user_info()
    return user_info or {}


def check_app_auth(session_token: str | None) -> dict | None:
    """Check if user has valid app authentication (non-throwing version).

    Args:
        session_token: Session cookie value

    Returns:
        Session data dict or None if not authenticated
    """
    if not session_token:
        return None

    session_manager = get_session_manager()
    return session_manager.verify_session_token(session_token)


def check_google_auth() -> bool:
    """Check if user has valid Google OAuth authentication.

    Returns:
        True if authenticated with Google
    """
    oauth_service = get_oauth_service()
    return oauth_service.is_authenticated()


async def get_current_user(
    session_data: dict = None,
) -> str:
    """Get current user ID from session.
    
    This is a dependency for extracting user_id from authenticated sessions.
    Use with Depends(require_app_auth) to ensure authentication.
    
    Args:
        session_data: Session data from require_app_auth (optional, for chaining)
        
    Returns:
        User ID string
        
    Raises:
        HTTPException: If user_id not found in session
    """
    if session_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    user_id = session_data.get("user_id") or session_data.get("username")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User identification not found",
        )

    return user_id


def get_current_user_from_session(session_data: dict) -> str:
    """Extract user_id from session data (non-async helper).
    
    Args:
        session_data: Session data dict
        
    Returns:
        User ID string or "anonymous" if not found
    """
    return session_data.get("user_id") or session_data.get("username") or "anonymous"
